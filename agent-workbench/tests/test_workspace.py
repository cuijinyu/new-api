"""Unit tests for app.runner.workspace — sandbox input directory assembly."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.runner.workspace import build_input, cleanup, collect_output, prepare_workspace


@pytest.fixture
def workdir(tmp_path):
    return tmp_path / "workspace"


class TestPrepareWorkspace:
    def test_creates_directories(self, workdir):
        dirs = prepare_workspace(workdir)
        assert dirs["input"].exists()
        assert dirs["skills"].exists()
        assert dirs["output"].exists()

    def test_returns_expected_keys(self, workdir):
        dirs = prepare_workspace(workdir)
        assert set(dirs.keys()) == {"input", "skills", "output"}


class TestBuildInput:
    def test_minimal_context(self, workdir):
        dirs = prepare_workspace(workdir)
        context = {"job": {"id": "job-test123", "type": "billing_run"}}
        manifest = build_input(context, dirs)
        assert "input/job.json" in manifest["input_files"]
        job_path = dirs["input"] / "job.json"
        assert job_path.exists()
        data = json.loads(job_path.read_text(encoding="utf-8"))
        assert data["id"] == "job-test123"

    def test_instructions_written(self, workdir):
        dirs = prepare_workspace(workdir)
        context = {
            "job": {},
            "instructions": "请按照 UTC+8 口径复核。",
        }
        manifest = build_input(context, dirs)
        assert "input/instructions.md" in manifest["input_files"]
        content = (dirs["input"] / "instructions.md").read_text(encoding="utf-8")
        assert "UTC+8" in content

    def test_billing_summary(self, workdir):
        dirs = prepare_workspace(workdir)
        context = {
            "job": {},
            "billing_summary": {"total_usd": 1234.56, "channels": []},
        }
        manifest = build_input(context, dirs)
        assert "input/billing_summary.json" in manifest["input_files"]

    def test_config_files(self, workdir):
        dirs = prepare_workspace(workdir)
        context = {
            "job": {},
            "pricing": {"model_a": 0.01},
            "discounts": {"channel_1": 0.9},
        }
        manifest = build_input(context, dirs)
        assert "input/config/pricing.json" in manifest["input_files"]
        assert "input/config/discounts.json" in manifest["input_files"]
        pricing_data = json.loads((dirs["input"] / "config" / "pricing.json").read_text(encoding="utf-8"))
        assert pricing_data["model_a"] == 0.01

    def test_supplier_files(self, workdir):
        dirs = prepare_workspace(workdir)
        context = {
            "job": {},
            "supplier_files": [
                {"filename": "vendor_bill.csv", "data": "row1,row2\n1,2"},
                {"filename": "contract.pdf", "data": b"\x00\x01\x02"},
            ],
        }
        manifest = build_input(context, dirs)
        assert "input/vendor_bill.csv" in manifest["input_files"]
        assert "input/contract.pdf" in manifest["input_files"]
        assert (dirs["input"] / "vendor_bill.csv").read_text(encoding="utf-8") == "row1,row2\n1,2"
        assert (dirs["input"] / "contract.pdf").read_bytes() == b"\x00\x01\x02"

    def test_supplier_file_without_data_skipped(self, workdir):
        dirs = prepare_workspace(workdir)
        context = {
            "job": {},
            "supplier_files": [{"filename": "empty.csv", "data": None}],
        }
        manifest = build_input(context, dirs)
        assert "input/empty.csv" not in manifest["input_files"]

    def test_experiences(self, workdir):
        dirs = prepare_workspace(workdir)
        context = {
            "job": {},
            "experiences": [{"id": "exp-1", "text": "过去发现折扣口径差异"}],
        }
        manifest = build_input(context, dirs)
        assert "input/experiences.json" in manifest["input_files"]

    def test_skills(self, workdir):
        dirs = prepare_workspace(workdir)
        context = {
            "job": {},
            "skills": [
                {"path": "vendor-reconcile/SKILL.md", "content": "# Skill\nDo stuff."},
            ],
        }
        manifest = build_input(context, dirs)
        assert "skills/vendor-reconcile/SKILL.md" in manifest["skill_files"]
        content = (dirs["skills"] / "vendor-reconcile" / "SKILL.md").read_text(encoding="utf-8")
        assert "Do stuff" in content

    def test_full_context(self, workdir):
        dirs = prepare_workspace(workdir)
        context = {
            "job": {"id": "job-full", "type": "agent_conversation"},
            "instructions": "Full test instructions.",
            "billing_summary": {"total_usd": 100},
            "pricing": {"m": 0.05},
            "discounts": {"c": 0.8},
            "supplier_files": [{"filename": "bill.csv", "data": "a,b\n1,2"}],
            "experiences": [{"id": "e1"}],
            "skills": [{"path": "s/SKILL.md", "content": "ok"}],
        }
        manifest = build_input(context, dirs)
        assert len(manifest["input_files"]) >= 6
        assert len(manifest["skill_files"]) == 1


class TestCollectOutput:
    def test_empty_output(self, workdir):
        dirs = prepare_workspace(workdir)
        result = collect_output(dirs["output"])
        assert result == []

    def test_collects_files(self, workdir):
        dirs = prepare_workspace(workdir)
        out = dirs["output"]
        (out / "report.md").write_text("# Report", encoding="utf-8")
        (out / "result.json").write_text("{}", encoding="utf-8")
        sub = out / "skill_draft"
        sub.mkdir()
        (sub / "SKILL.md").write_text("# Skill", encoding="utf-8")
        result = collect_output(out)
        names = [rel for rel, _ in result]
        assert "report.md" in names
        assert "result.json" in names
        assert "skill_draft/SKILL.md" in names

    def test_nonexistent_dir(self, tmp_path):
        result = collect_output(tmp_path / "no_such_dir")
        assert result == []


class TestCleanup:
    def test_removes_tree(self, workdir):
        dirs = prepare_workspace(workdir)
        (dirs["input"] / "job.json").write_text("{}", encoding="utf-8")
        cleanup(workdir)
        assert not workdir.exists()

    def test_handles_missing(self, tmp_path):
        cleanup(tmp_path / "nonexistent")
