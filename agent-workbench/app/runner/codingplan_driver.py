#!/usr/bin/env python3
"""CodingPlan 真实驱动脚本 — 在沙箱或本地子进程中运行。

读取 INPUT_DIR 中的上下文文件，调用 Zhipu CodingPlan API 进行多轮对话+工具调用，
将结果写入 OUTPUT_DIR/result.json（及可选的 report.md / config_change_request.json）。

环境变量（由 runner 注入）：
  ZHIPU_CODINGPLAN_API_KEY  — 必需
  ZHIPU_CODINGPLAN_ENDPOINT — 可选，默认 https://open.bigmodel.cn/api/coding/paas/v4/chat/completions
  ZHIPU_CODINGPLAN_MODEL    — 可选，默认 glm-5.2
  INPUT_DIR / OUTPUT_DIR / WORKSPACE_DIR — workspace 路径
"""

from __future__ import annotations

import json
import os
import sys
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


API_KEY = env("ZHIPU_CODINGPLAN_API_KEY")
ENDPOINT = env("ZHIPU_CODINGPLAN_ENDPOINT", "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions")
MODEL = env("ZHIPU_CODINGPLAN_MODEL", "glm-5.2")
INPUT_DIR = Path(env("INPUT_DIR", "/workspace/input"))
OUTPUT_DIR = Path(env("OUTPUT_DIR", "/workspace/output"))
MAX_TOOL_ROUNDS = 10
REQUEST_TIMEOUT = 120


# ---------------------------------------------------------------------------
# 文件读取工具 — 让 CodingPlan 通过 tool_call 读取 input/ 中的文件
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "file_read",
            "description": "读取工作目录中的文件内容。path 相对于 workspace 根目录，如 input/billing_summary.json",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对路径，如 input/job.json 或 input/config/pricing.json"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_list",
            "description": "列出工作目录中指定目录下的文件列表",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "相对路径目录，如 input 或 input/config"},
                },
                "required": ["directory"],
            },
        },
    },
]


def handle_tool_call(name: str, arguments: dict[str, Any]) -> str:
    """执行工具调用，返回结果文本。"""
    workspace_dir = Path(env("WORKSPACE_DIR", str(INPUT_DIR.parent)))

    if name == "file_read":
        rel_path = arguments.get("path", "")
        target = (workspace_dir / rel_path).resolve()
        # 安全检查：不允许读取 workspace 外的文件
        try:
            target.relative_to(workspace_dir.resolve())
        except ValueError:
            return f"错误：路径 {rel_path} 不在工作目录内"
        if not target.exists():
            return f"文件不存在：{rel_path}"
        if target.is_dir():
            return f"这是一个目录，请用 file_list 列出其内容"
        try:
            content = target.read_text(encoding="utf-8")
            if len(content) > 50000:
                content = content[:50000] + "\n...(截断，文件过大)"
            return content
        except UnicodeDecodeError:
            return f"文件 {rel_path} 是二进制文件，无法读取文本内容"

    elif name == "file_list":
        directory = arguments.get("directory", "input")
        target = (workspace_dir / directory).resolve()
        try:
            target.relative_to(workspace_dir.resolve())
        except ValueError:
            return f"错误：路径 {directory} 不在工作目录内"
        if not target.exists() or not target.is_dir():
            return f"目录不存在：{directory}"
        entries = []
        for item in sorted(target.iterdir()):
            suffix = "/" if item.is_dir() else f" ({item.stat().st_size} bytes)"
            entries.append(f"  {item.name}{suffix}")
        return "\n".join(entries) if entries else "(空目录)"

    return f"未知工具：{name}"


# ---------------------------------------------------------------------------
# 系统 prompt 组装
# ---------------------------------------------------------------------------

def build_system_prompt() -> str:
    parts = [
        "你是一个专业的账单对账分析 Agent。你的任务是分析供应商账单与内部生成账单之间的差异，",
        "找出差异原因，评估影响金额，并给出处理建议。",
        "所有对账均基于刊例价进行；折扣只用于差异解释、影响测算或处理建议，不改变对账基准。",
        "",
        "你可以使用以下工具读取工作目录中的资料：",
        "- file_read(path): 读取指定文件",
        "- file_list(directory): 列出目录内容",
        "",
        "工作目录结构：",
        "  input/job.json          — 任务描述",
        "  input/instructions.md   — 详细指令",
        "  input/billing_summary.json — 内部账单汇总",
        "  input/config/pricing.json  — 计费口径",
        "  input/config/discounts.json — 折扣配置",
        "  input/experiences.json  — 历史经验",
        "  input/（其他文件）       — 供应商账单等上传资料",
        "",
        "完成分析后，请输出 JSON 格式的结论（我会从你的回复中提取）：",
        "所有需要给用户查看或下载的文件都必须写入 `output/` 下；`result_files` 只能引用 `output/` 下的相对路径，Workbench 会自动上传到 S3 并在页面“产物”区提供下载。",
        '```json',
        '{',
        '  "_output_contract": "Write downloadable files under output/. Use output/<relative-path> in result_files.",',
        '  "status": "completed|needs_info",',
        '  "result_files": [{"label": "报告", "path": "output/report.md", "role": "report"}],',
        '  "summary": "一句话总结",',
        '  "reason": "差异原因详述",',
        '  "impact": {"amount_usd_delta": 数字, "amount_cny_delta": 数字},',
        '  "recommended_actions": ["建议动作1", "建议动作2"],',
        '  "saveable_experience": "可沉淀的经验描述（如有）",',
        '  "config_change": null 或 {"type": "pricing|discount", "changes": [...]}',
        '}',
        '```',
    ]
    return "\n".join(parts)


def build_user_message() -> str:
    """读取 instructions.md 作为用户消息，附带可用文件列表。"""
    instructions_path = INPUT_DIR / "instructions.md"
    if instructions_path.exists():
        instructions = instructions_path.read_text(encoding="utf-8")
    else:
        instructions = "请分析当前对账任务，找出差异原因并给出建议。"

    # 附带文件列表帮助 agent 了解有哪些资料可用
    workspace_dir = Path(env("WORKSPACE_DIR", str(INPUT_DIR.parent)))
    available_files: list[str] = []
    for base in ("input", "skills"):
        base_dir = workspace_dir / base
        if base_dir.exists():
            for f in sorted(base_dir.rglob("*")):
                if f.is_file():
                    available_files.append(f.relative_to(workspace_dir).as_posix())

    file_list = "\n".join(f"  - {f}" for f in available_files[:30])
    conversation_lines: list[str] = []
    conversation_path = INPUT_DIR / "conversation.jsonl"
    if conversation_path.exists():
        for raw_line in conversation_path.read_text(encoding="utf-8").splitlines()[-20:]:
            try:
                turn = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            role = str(turn.get("role") or "user")
            content = str(turn.get("content") or "").strip()
            if content:
                conversation_lines.append(f"{role}: {content[:4000]}")
    conversation_text = "\n".join(conversation_lines) if conversation_lines else "(暂无)"
    return f"{instructions}\n\n当前对话：\n{conversation_text}\n\n可用文件：\n{file_list}"


# ---------------------------------------------------------------------------
# API 调用
# ---------------------------------------------------------------------------

def call_api(messages: list[dict[str, Any]], *, tools: list[dict] | None = None) -> dict[str, Any]:
    """同步调用 CodingPlan API（非流式），返回完整响应。"""
    payload: dict[str, Any] = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.2,
        "stream": False,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"CodingPlan API HTTP {exc.code}: {body}") from exc


def extract_message(response: dict[str, Any]) -> dict[str, Any]:
    """从 API 响应中提取 assistant message。"""
    choices = response.get("choices") or []
    if not choices:
        return {"role": "assistant", "content": "（API 未返回内容）"}
    return choices[0].get("message") or {"role": "assistant", "content": ""}


# ---------------------------------------------------------------------------
# 结果解析
# ---------------------------------------------------------------------------

def extract_result_json(content: str) -> dict[str, Any]:
    """从 assistant 回复中提取 JSON 结论块。"""
    # 尝试从 ```json ... ``` 中提取
    import re
    matches = re.findall(r"```(?:json)?\s*\n(.*?)```", content, re.DOTALL)
    for match in matches:
        try:
            parsed = json.loads(match)
            if isinstance(parsed, dict) and ("status" in parsed or "summary" in parsed):
                return parsed
        except json.JSONDecodeError:
            continue

    # 尝试整个回复作为 JSON
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # 无法提取结构化结果，用回复文本兜底
    return {
        "status": "completed",
        "summary": content[:200] if content else "分析完成",
        "reason": content,
        "impact": {},
        "recommended_actions": ["请查看完整分析报告"],
    }


# ---------------------------------------------------------------------------
# 主执行流程
# ---------------------------------------------------------------------------

def run() -> int:
    if not API_KEY:
        write_error_result("ZHIPU_CODINGPLAN_API_KEY 未配置，无法执行 CodingPlan")
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": build_system_prompt()},
        {"role": "user", "content": build_user_message()},
    ]

    full_content = ""
    try:
        for round_idx in range(MAX_TOOL_ROUNDS + 1):
            response = call_api(messages, tools=TOOLS if round_idx < MAX_TOOL_ROUNDS else None)
            assistant_msg = extract_message(response)
            messages.append(assistant_msg)

            tool_calls = assistant_msg.get("tool_calls")
            if not tool_calls:
                full_content = assistant_msg.get("content") or ""
                break

            # 处理工具调用
            for tc in tool_calls:
                func = tc.get("function") or {}
                name = func.get("name", "")
                try:
                    args = json.loads(func.get("arguments", "{}"))
                except json.JSONDecodeError:
                    args = {}

                result = handle_tool_call(name, args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": result,
                })
        else:
            full_content = messages[-1].get("content") or "达到最大轮次限制"

    except Exception as exc:
        write_error_result(f"执行异常：{exc}\n{traceback.format_exc()}")
        return 1

    # 写入结果
    result = extract_result_json(full_content)
    result.setdefault("status", "completed")
    result.setdefault("result_files", [{"label": "报告", "path": "output/report.md", "role": "report"}])
    write_json(OUTPUT_DIR / "result.json", result)

    # 如果有 config_change 建议，写入独立文件
    config_change = result.pop("config_change", None)
    if config_change and isinstance(config_change, dict):
        write_json(OUTPUT_DIR / "config_change_request.json", {
            "type": config_change.get("type", "pricing"),
            "reason": result.get("reason", ""),
            "changes": config_change.get("changes", []),
            "impact": result.get("impact", {}),
        })

    # 写入 report.md
    report_lines = [
        f"# 对账分析报告\n",
        f"## 结论\n{result.get('summary', '')}\n",
        f"## 差异原因\n{result.get('reason', '')}\n",
        f"## 建议动作\n",
    ]
    for action in result.get("recommended_actions") or []:
        report_lines.append(f"- {action}")
    if result.get("saveable_experience"):
        report_lines.append(f"\n## 可沉淀经验\n{result['saveable_experience']}")
    write_text(OUTPUT_DIR / "report.md", "\n".join(report_lines))

    print(f"[codingplan_driver] 完成，status={result.get('status')}", file=sys.stderr)
    return 0


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_error_result(message: str) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_json(OUTPUT_DIR / "result.json", {
        "status": "error",
        "summary": message,
        "reason": message,
        "impact": {},
        "recommended_actions": ["检查配置并重试"],
    })
    print(f"[codingplan_driver] 错误：{message}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(run())
