#!/usr/bin/env python3
"""价格一致性校验：Go 计费配置 vs Athena 对账价（pricing.json / discounts.json）。

目的
----
新增模型或调整定价后，Go 运行时计费（扁平 model_ratio / 分段 tiered / 图片专用价）
与 Athena 对账侧的 pricing.json / discounts.json 之间容易出现“漏配 / 类型不一致”，
导致对账落到默认 quota/500000 或 flat 兜底而算错账。本脚本做静态一致性校验，
非零退出码用于在出账前（bill_cron）告警。

校验项
------
  (b) Go 分段模型（defaultTieredPricing）必须在 pricing.json 中存在且 type=tiered。
      缺失或类型错配 -> ERROR（对账无法重算分段价）。
  (c) pricing.json 标记 tiered 的模型，若 Go 未标记分段 -> WARNING（可能是仅对账用，或 Go 漏配）。
  (d) Go 图片模型（imageRatio / imageCompletionRatio，及 dall-e/gpt-image/multimodal 等
      图像生成名）在 pricing.json 中缺少 multimodal 条目 -> WARNING（图片 token 重算需 op_image）。
  (a) discounts.json 基础结构（cost/revenue defaults）缺失 -> ERROR。
  (e)（可选）同名模型 Go 分段档位数 vs pricing.json tiers 数量漂移 -> WARNING。

用法
----
  python check_pricing_coverage.py            # 打印报告，有 ERROR 则 exit 1
  python check_pricing_coverage.py --json      # 机器可读输出
  python check_pricing_coverage.py --warn-only # 仅告警，始终 exit 0（cron 前置检查用）

被 bill_cron 出账前调用（warn 模式）做兜底告警。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

if sys.stdout and sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# scripts/athena/ -> repo root 上两级
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parents[1]

_MODEL_RATIO_GO = _REPO_ROOT / "setting" / "ratio_setting" / "model_ratio.go"
_TIERED_GO = _REPO_ROOT / "setting" / "ratio_setting" / "tiered_pricing.go"
_PRICING_JSON = _SCRIPT_DIR / "pricing.json"
_DISCOUNTS_JSON = _SCRIPT_DIR / "discounts.json"

# 图像生成 / 图片类模型名特征，与 Go controller 的 isImageModel 关键字保持一致
_IMAGE_NAME_KEYWORDS = (
    "dall-e", "dalle", "gpt-image", "stable-diffusion", "sdxl", "flux",
    "midjourney", "imagen", "ideogram", "recraft", "playground-v",
    "kolors", "seedream", "seededit", "hunyuan-image", "nano-banana",
    "qwen-image", "wan2", "wan-",
)


# ---------------------------------------------------------------------------
# Go 源解析：提取 map[string]... 字面量的顶层字符串 key
# ---------------------------------------------------------------------------

def extract_go_map_keys(text: str, var_name: str) -> set[str]:
    """提取 `var <var_name> = map[string]...{ ... }` 字面量里的顶层（depth==1）字符串 key。

    适用于值为标量（float）或嵌套结构（{...}）的 map：嵌套块内的内容因 depth>1 被跳过。
    """
    m = re.search(r"var\s+" + re.escape(var_name) + r"\b", text)
    if not m:
        return set()
    try:
        start = text.index("{", m.end())
    except ValueError:
        return set()

    keys: set[str] = set()
    depth = 0
    pos = start
    n = len(text)

    while pos < n:
        ch = text[pos]

        if ch == "/" and pos + 1 < n and text[pos + 1] == "/":
            eol = text.find("\n", pos)
            pos = n if eol == -1 else eol
            continue

        if ch == "{":
            depth += 1
            pos += 1
            continue

        if ch == "}":
            depth -= 1
            pos += 1
            if depth == 0:
                break
            continue

        if ch == '"' and depth == 1:
            j = pos + 1
            buf = []
            while j < n and text[j] != '"':
                if text[j] == "\\" and j + 1 < n:
                    buf.append(text[j + 1])
                    j += 2
                    continue
                buf.append(text[j])
                j += 1
            key = "".join(buf)
            # 仅当其后（忽略空白）紧跟 ':' 时才视为 map key
            k = j + 1
            while k < n and text[k] in " \t":
                k += 1
            if k < n and text[k] == ":":
                keys.add(key)
            pos = j + 1
            continue

        pos += 1

    return keys


def count_go_tiered_tiers(text: str) -> dict[str, int]:
    """粗略统计 defaultTieredPricing 中每个模型的 PriceTier 档位数量（用于漂移检查）。"""
    m = re.search(r"var\s+defaultTieredPricing\b", text)
    if not m:
        return {}
    try:
        start = text.index("{", m.end())
    except ValueError:
        return {}

    counts: dict[str, int] = {}
    depth = 0
    pos = start
    n = len(text)
    current_model: str | None = None

    while pos < n:
        ch = text[pos]

        if ch == "/" and pos + 1 < n and text[pos + 1] == "/":
            eol = text.find("\n", pos)
            pos = n if eol == -1 else eol
            continue

        if ch == '"' and depth == 1:
            j = pos + 1
            buf = []
            while j < n and text[j] != '"':
                buf.append(text[j])
                j += 1
            key = "".join(buf)
            k = j + 1
            while k < n and text[k] in " \t":
                k += 1
            if k < n and text[k] == ":":
                current_model = key
                counts.setdefault(current_model, 0)
            pos = j + 1
            continue

        if ch == "{":
            depth += 1
            pos += 1
            continue
        if ch == "}":
            depth -= 1
            pos += 1
            if depth == 0:
                break
            continue

        # PriceTier 元素出现在 Tiers: []PriceTier{ {...}, {...} }，以 "MinTokens" 字段计数
        if current_model and depth >= 2 and text.startswith("MinTokens", pos):
            counts[current_model] = counts.get(current_model, 0) + 1
            pos += len("MinTokens")
            continue

        pos += 1

    return counts


# ---------------------------------------------------------------------------
# 数据加载
# ---------------------------------------------------------------------------

def load_go_sets() -> dict:
    model_ratio_text = _MODEL_RATIO_GO.read_text(encoding="utf-8")
    tiered_text = _TIERED_GO.read_text(encoding="utf-8")

    flat = extract_go_map_keys(model_ratio_text, "defaultModelRatio")
    model_price = extract_go_map_keys(model_ratio_text, "defaultModelPrice")
    image_ratio = extract_go_map_keys(model_ratio_text, "defaultImageRatio")
    image_completion = extract_go_map_keys(model_ratio_text, "defaultImageCompletionRatio")
    tiered = extract_go_map_keys(tiered_text, "defaultTieredPricing")
    tier_counts = count_go_tiered_tiers(tiered_text)

    # 图片模型集 = image ratio/completion 命中 + 名称特征命中（在 flat/price 集合里）
    image_models = set(image_ratio) | set(image_completion)
    for name in flat | model_price:
        lower = name.lower()
        if any(kw in lower for kw in _IMAGE_NAME_KEYWORDS):
            image_models.add(name)

    return {
        "flat": flat,
        "model_price": model_price,
        "image_ratio": image_ratio,
        "image_completion": image_completion,
        "image_models": image_models,
        "tiered": tiered,
        "tier_counts": tier_counts,
    }


def load_pricing() -> dict:
    data = json.loads(_PRICING_JSON.read_text(encoding="utf-8"))
    tiered: dict[str, dict] = {}
    flat: set[str] = set()
    multimodal: set[str] = set()
    for entry in data.get("models", []):
        name = entry.get("name")
        if not name:
            continue
        typ = entry.get("type")
        if typ == "tiered":
            tiered[name] = entry
        elif typ == "multimodal":
            multimodal.add(name)
        else:
            flat.add(name)
    return {"tiered": tiered, "flat": flat, "multimodal": multimodal, "all": data}


def load_discounts() -> dict:
    return json.loads(_DISCOUNTS_JSON.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------

def run_checks() -> dict:
    """执行全部校验，返回 {errors, warnings, infos}（均为字符串列表）。"""
    errors: list[str] = []
    warnings: list[str] = []
    infos: list[str] = []

    go = load_go_sets()
    pricing = load_pricing()
    discounts = load_discounts()

    pricing_tiered = pricing["tiered"]
    pricing_multimodal = pricing["multimodal"]

    # (b) Go 分段模型必须在 pricing.json 中且 type=tiered
    for model in sorted(go["tiered"]):
        if model in pricing_tiered:
            continue
        if model in pricing["flat"] or model in pricing_multimodal:
            errors.append(
                f"[tiered-type] Go 标记分段的模型 '{model}' 在 pricing.json 中类型不是 tiered，"
                f"对账会用错计费方式")
        else:
            errors.append(
                f"[tiered-missing] Go 标记分段的模型 '{model}' 缺失 pricing.json 条目，"
                f"对账无法重算分段价（将回退 quota/flat）")

    # (c) pricing.json tiered 但 Go 未标记分段
    for model in sorted(pricing_tiered.keys()):
        if model not in go["tiered"]:
            warnings.append(
                f"[tiered-reverse] pricing.json 中 '{model}' 为 tiered，但 Go defaultTieredPricing 未包含，"
                f"请确认是否 Go 漏配或仅用于对账")

    # (e) 同名模型档位数漂移（可选）
    for model, entry in pricing_tiered.items():
        if model in go["tier_counts"]:
            go_n = go["tier_counts"][model]
            json_n = len(entry.get("tiers", []))
            if go_n and json_n and go_n != json_n:
                warnings.append(
                    f"[tier-drift] '{model}' Go 档位数={go_n} 与 pricing.json tiers 数={json_n} 不一致")

    # (d) Go 图片模型缺 pricing.json multimodal 条目
    for model in sorted(go["image_models"]):
        if model not in pricing_multimodal and model not in pricing_tiered and model not in pricing["flat"]:
            warnings.append(
                f"[image-missing] Go 图片模型 '{model}' 在 pricing.json 无对应条目，"
                f"图片 token 重算/对账会回退默认（如需精确对账请补 multimodal 条目）")

    # (a) discounts.json 基础结构
    cost = discounts.get("cost_discounts", {})
    rev = discounts.get("revenue_discounts", {})
    if "defaults" not in cost or "*" not in cost.get("defaults", {}):
        errors.append("[discounts] cost_discounts.defaults['*'] 缺失（成本折扣无默认值）")
    if "defaults" not in rev or "*" not in rev.get("defaults", {}):
        errors.append("[discounts] revenue_discounts.defaults['*'] 缺失（客户折扣无默认值）")

    infos.append(
        f"Go: flat={len(go['flat'])} tiered={len(go['tiered'])} "
        f"image={len(go['image_models'])} model_price={len(go['model_price'])}")
    infos.append(
        f"pricing.json: tiered={len(pricing_tiered)} flat={len(pricing['flat'])} "
        f"multimodal={len(pricing_multimodal)}")

    return {"errors": errors, "warnings": warnings, "infos": infos}


def format_report(result: dict) -> str:
    lines = ["=== 价格一致性校验 ==="]
    for info in result["infos"]:
        lines.append(f"  - {info}")
    if result["errors"]:
        lines.append(f"\n[ERROR] {len(result['errors'])} 项：")
        lines.extend(f"  x {e}" for e in result["errors"])
    if result["warnings"]:
        lines.append(f"\n[WARN] {len(result['warnings'])} 项：")
        lines.extend(f"  ! {w}" for w in result["warnings"])
    if not result["errors"] and not result["warnings"]:
        lines.append("\n全部通过：无不一致项。")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="价格一致性校验")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    parser.add_argument("--warn-only", action="store_true",
                        help="仅告警，始终 exit 0（cron 前置检查用）")
    args = parser.parse_args()

    result = run_checks()

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_report(result))

    if args.warn_only:
        return 0
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
