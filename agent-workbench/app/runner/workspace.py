"""沙箱/本地工作目录组装与产物回收。

目录契约（与 runner/fake_agent.py、docs/job-model.md 保持一致）：
  workspace/
    input/      只读上下文：job.json / instructions.md / billing_summary.json /
                config/pricing.json+discounts.json / 上传的供应商文件
    skills/     引用的历史经验 / skills（只读）
    output/     agent 回收产物：report.md / result.json /
                config_change_request.json / skill_draft/ / 证据文件
"""

from __future__ import annotations

import json
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Any


class _SafeEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, datetime):
            return o.isoformat().replace("+00:00", "Z")
        if isinstance(o, date):
            return o.isoformat()
        if isinstance(o, Path):
            return str(o)
        return super().default(o)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, cls=_SafeEncoder) + "\n", encoding="utf-8")


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def prepare_workspace(workdir: Path) -> dict[str, Path]:
    input_dir = workdir / "input"
    skills_dir = workdir / "skills"
    output_dir = workdir / "output"
    for directory in (input_dir, skills_dir, output_dir):
        directory.mkdir(parents=True, exist_ok=True)
    return {"input": input_dir, "skills": skills_dir, "output": output_dir}


def build_input(context: dict[str, Any], dirs: dict[str, Path]) -> dict[str, Any]:
    """把 main 准备好的上下文落到 input/ 与 skills/，返回组装清单（用于审计/断言）。"""
    input_dir = dirs["input"]
    skills_dir = dirs["skills"]

    manifest: dict[str, Any] = {"input_files": [], "skill_files": []}

    job = context.get("job") or {}
    _write_json(input_dir / "job.json", job)
    manifest["input_files"].append("input/job.json")

    instructions = context.get("instructions")
    if instructions:
        _write_text(input_dir / "instructions.md", str(instructions))
        manifest["input_files"].append("input/instructions.md")

    billing_summary = context.get("billing_summary")
    if billing_summary is not None:
        _write_json(input_dir / "billing_summary.json", billing_summary)
        manifest["input_files"].append("input/billing_summary.json")

    pricing = context.get("pricing")
    discounts = context.get("discounts")
    if pricing is not None:
        _write_json(input_dir / "config" / "pricing.json", pricing)
        manifest["input_files"].append("input/config/pricing.json")
    if discounts is not None:
        _write_json(input_dir / "config" / "discounts.json", discounts)
        manifest["input_files"].append("input/config/discounts.json")

    for supplier in context.get("supplier_files") or []:
        filename = supplier.get("filename") or "supplier_file"
        data = supplier.get("data")
        if data is None:
            continue
        target = input_dir / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, str):
            target.write_text(data, encoding="utf-8")
        else:
            target.write_bytes(data)
        manifest["input_files"].append(f"input/{filename}")

    experiences = context.get("experiences") or []
    if experiences:
        _write_json(input_dir / "experiences.json", experiences)
        manifest["input_files"].append("input/experiences.json")

    for index, skill in enumerate(context.get("skills") or []):
        rel = skill.get("path") or f"skill_{index}/SKILL.md"
        content = skill.get("content") or ""
        target = skills_dir / rel
        _write_text(target, content)
        manifest["skill_files"].append(f"skills/{rel}")

    return manifest


def collect_output(output_dir: Path) -> list[tuple[str, Path]]:
    """收集 output/ 下的全部文件，返回 (相对路径, 绝对路径)。"""
    if not output_dir.exists():
        return []
    files: list[tuple[str, Path]] = []
    for path in sorted(output_dir.rglob("*")):
        if path.is_file():
            files.append((path.relative_to(output_dir).as_posix(), path))
    return files


def cleanup(workdir: Path) -> None:
    shutil.rmtree(workdir, ignore_errors=True)
