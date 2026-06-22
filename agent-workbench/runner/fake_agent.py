#!/usr/bin/env python3
"""Deterministic fake agent for local Agent Workbench E2E.

The fake agent deliberately avoids LLM calls. It reads `/workspace/input` and
`/workspace/skills`, then writes the artifact contract expected by the
Workbench runner.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Any


FIXED_GENERATED_AT = "2026-06-19T00:00:00Z"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def as_money(value: Any) -> float:
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return 0.0


def stable_id(prefix: str, payload: Any) -> str:
    # 固定输入生成固定 ID，避免本地 E2E 因随机值导致快照/断言不稳定。
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(encoded).hexdigest()[:12]}"


def summarize_diff(rows: list[dict[str, str]]) -> dict[str, Any]:
    # fake-agent 只关心对账差异摘要，不尝试复刻真实 LLM 的推理过程。
    anomalous = [
        row
        for row in rows
        if abs(as_money(row.get("delta_usd"))) >= 0.01 or row.get("status", "").lower() != "matched"
    ]
    return {
        "total_delta_usd": round(sum(as_money(row.get("delta_usd")) for row in rows), 6),
        "anomaly_count": len(anomalous),
        "models": sorted({row.get("model", "unknown") for row in anomalous}),
        "largest_abs_delta_usd": max([abs(as_money(row.get("delta_usd"))) for row in rows] or [0.0]),
    }


def derive_diff_rows(input_dir: Path, billing_summary: dict[str, Any]) -> list[dict[str, str]]:
    # 从上传的供应商 CSV 推导一份确定性对账明细（无供应商文件时给出 matched 占位）。
    supplier_rows: list[dict[str, str]] = []
    for candidate in sorted(input_dir.glob("*.csv")):
        if candidate.name in {"diff.csv", "anomalies.csv", "supplier_diff.csv"}:
            continue
        supplier_rows = read_csv(candidate)
        if supplier_rows:
            break
    rows: list[dict[str, str]] = []
    for row in supplier_rows:
        model = row.get("model") or row.get("Model") or "unknown"
        supplier_usd = as_money(row.get("total_usd") or row.get("supplier_usd") or row.get("amount_usd"))
        expected_usd = supplier_usd  # fake-agent 假定本地账单与供应商一致，差异交给真实 agent。
        rows.append(
            {
                "model": model,
                "expected_usd": f"{expected_usd:.2f}",
                "supplier_usd": f"{supplier_usd:.2f}",
                "delta_usd": f"{(supplier_usd - expected_usd):.2f}",
                "status": "matched",
            }
        )
    if not rows:
        rows.append(
            {
                "model": "claude-opus-4-6",
                "expected_usd": "100.00",
                "supplier_usd": "100.00",
                "delta_usd": "0.00",
                "status": "matched",
            }
        )
    return rows


def write_diff_evidence(output_dir: Path, diff_rows: list[dict[str, str]], diff_summary: dict[str, Any]) -> None:
    diff_header = ["model", "expected_usd", "supplier_usd", "delta_usd", "status"]
    lines = [",".join(diff_header)]
    for row in diff_rows:
        lines.append(",".join(str(row.get(col, "")) for col in diff_header))
    write_text(output_dir / "diff.csv", "\n".join(lines) + "\n")

    anomalies = [
        row
        for row in diff_rows
        if abs(as_money(row.get("delta_usd"))) >= 0.01 or str(row.get("status", "")).lower() != "matched"
    ]
    anom_lines = ["severity,model,reason,delta_usd"]
    if anomalies:
        for row in anomalies:
            anom_lines.append(
                f"warning,{row.get('model', 'unknown')},supplier delta detected,{row.get('delta_usd', '0.00')}"
            )
    else:
        anom_lines.append("info,-,no anomaly above tolerance,0.00")
    write_text(output_dir / "anomalies.csv", "\n".join(anom_lines) + "\n")


def skill_headings(skills_dir: Path) -> list[str]:
    # 模拟真实 Agent 启动时加载既有 Skills，报告里会记录本次使用了哪些经验。
    headings: list[str] = []
    for skill_file in sorted(skills_dir.rglob("SKILL.md")):
        title = None
        for line in skill_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("#"):
                title = line.strip("# ").strip()
                break
        headings.append(title or str(skill_file.relative_to(skills_dir)))
    return headings


def build_report(job: dict[str, Any], diff_summary: dict[str, Any], loaded_skills: list[str]) -> str:
    vendor = job.get("vendor", "1001AI")
    month = job.get("month", "2026-06")
    channel_id = job.get("channel_id", 65)
    models = ", ".join(diff_summary["models"]) or "none"
    skills = ", ".join(loaded_skills) or "none"
    delta = diff_summary["total_delta_usd"]
    return "\n".join(
        [
            "# Agent Workbench Fake Investigation Report",
            "",
            f"- Generated at: {FIXED_GENERATED_AT}",
            f"- Vendor: {vendor}",
            f"- Month: {month}",
            f"- Channel ID: {channel_id}",
            f"- Loaded skills: {skills}",
            "",
            "## Finding",
            "",
            (
                "The fixture supplier bill differs from the local billing output "
                f"by {delta:.2f} USD. The deterministic recommendation is to "
                "create a Claude-family channel discount rule for review."
            ),
            "",
            "## Evidence",
            "",
            f"- Anomaly rows: {diff_summary['anomaly_count']}",
            f"- Affected models: {models}",
            f"- Largest absolute row delta: {diff_summary['largest_abs_delta_usd']:.2f} USD",
            "",
            "## Recommendation",
            "",
            "Apply the generated config change request, then rerun billing with the new config version.",
            "",
        ]
    )


def build_skill(job: dict[str, Any], diff_summary: dict[str, Any]) -> str:
    vendor = job.get("vendor", "1001AI")
    channel_id = job.get("channel_id", 65)
    return "\n".join(
        [
            f"# {vendor} Vendor Reconcile",
            "",
            "Use this skill when reconciling 1001AI supplier invoices against Athena billing output.",
            "",
            "## Procedure",
            "",
            "1. Load the normalized supplier bill and local billing detail for the same month.",
            "2. Join rows by request_id when available, otherwise by model, day, and token counts.",
            "3. Flag rows where the USD delta is non-zero or status is not matched.",
            f"4. For channel {channel_id}, treat Claude-family deltas as discount-rule candidates.",
            "5. Draft config_change_request.json instead of mutating production config directly.",
            "",
            "## Fixture Expectation",
            "",
            f"- Expected anomaly count: {diff_summary['anomaly_count']}",
            f"- Expected total delta USD: {diff_summary['total_delta_usd']:.2f}",
            "",
        ]
    )


def main() -> int:
    # 目录契约和 OpenSandbox 容器保持一致：input/skills 只读，output 写回给 Workbench。
    workspace = Path(os.environ.get("WORKSPACE_DIR", "/workspace"))
    input_dir = Path(os.environ.get("INPUT_DIR", str(workspace / "input")))
    skills_dir = Path(os.environ.get("SKILLS_DIR", str(workspace / "skills")))
    output_dir = Path(os.environ.get("OUTPUT_DIR", str(workspace / "output")))

    job = read_json(input_dir / "job.json", {})
    billing_summary = read_json(input_dir / "billing_summary.json", {})
    # 真实 agent 会读取上传的供应商资料自行核对；fake-agent 用确定性规则产出证据文件。
    diff_rows = read_csv(input_dir / "diff.csv") or read_csv(input_dir / "supplier_diff.csv")
    if not diff_rows:
        diff_rows = derive_diff_rows(input_dir, billing_summary)
    diff_summary = summarize_diff(diff_rows)
    loaded_skills = skill_headings(skills_dir)

    month = job.get("month", billing_summary.get("month", "2026-06"))
    channel_id = int(job.get("channel_id", billing_summary.get("channel_id", 65)))
    vendor = job.get("vendor", "1001AI")
    job_id = job.get("job_id", "job-fake-agent-e2e")

    change_request = {
        # Agent 只产出配置变更建议，不能在沙箱内直接修改 DB 或正式配置；不做阻塞审批。
        "type": "discount",
        "status": "open",
        "proposed_by": "fake-agent",
        "job_id": job_id,
        "reason": f"{vendor} supplier bill fixture indicates a Claude discount update.",
        "changes": [
            {
                "action": "create_discount_rule",
                "scope_type": "channel",
                "vendor": vendor,
                "channel_id": channel_id,
                "model_pattern": "claude-*",
                "discount_type": "multiplier",
                "discount_value_json": {"multiplier": 0.82},
                "effective_from": f"{month}-01",
                "effective_to": None,
            }
        ],
        "evidence": [
            "input/diff.csv",
            "input/billing_summary.json",
            "input/supplier_1001ai_2026_06.csv",
        ],
        "impact_summary": {
            "month": month,
            "channel_id": channel_id,
            "vendor": vendor,
            "amount_usd_delta": diff_summary["total_delta_usd"],
            "anomaly_count": diff_summary["anomaly_count"],
        },
    }
    change_request["id"] = stable_id("ccr", change_request)

    result = {
        "status": "completed",
        "summary": "Deterministic fake agent generated a discount change request.",
        "requires_approval": False,
        "config_change_request_id": change_request["id"],
        "config_change_request_path": "output/config_change_request.json",
        "report_path": "output/report.md",
        "skill_draft_path": "output/skill_draft/SKILL.md",
        "impact": change_request["impact_summary"],
        "recommended_next_job": "billing_rerun_after_suggestion",
        "generated_at": FIXED_GENERATED_AT,
    }

    write_text(output_dir / "report.md", build_report(job, diff_summary, loaded_skills))
    write_diff_evidence(output_dir, diff_rows, diff_summary)
    write_json(output_dir / "result.json", result)
    write_json(output_dir / "config_change_request.json", change_request)
    write_json(output_dir / "impact_summary.json", change_request["impact_summary"])
    write_text(output_dir / "skill_draft" / "SKILL.md", build_skill(job, diff_summary))
    write_json(
        output_dir / "skill_draft" / "manifest.json",
        {
            "name": f"{vendor} Vendor Reconcile",
            "version": "v1",
            "vendor": vendor,
            "tags": ["billing", "reconcile", "fake-agent", "e2e"],
            "created_from_job": job_id,
            "entrypoint": "SKILL.md",
            "status": "draft",
            "generated_at": FIXED_GENERATED_AT,
        },
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
