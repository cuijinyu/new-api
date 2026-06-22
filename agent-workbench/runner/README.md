# Agent Workbench Runner

This directory contains the local runner pieces used by the Docker E2E stack.

`fake_agent.py` is deterministic and does not call an LLM. It reads:

```text
/workspace/input
/workspace/skills
/workspace/instructions.md
```

and writes:

```text
/workspace/output/report.md
/workspace/output/result.json
/workspace/output/config_change_request.json
/workspace/output/impact_summary.json
/workspace/output/skill_draft/SKILL.md
```

Local smoke command:

```bash
docker compose -f agent-workbench/docker-compose.e2e.yml run --rm fake-agent
```
