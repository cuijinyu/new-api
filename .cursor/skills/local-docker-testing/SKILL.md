---
name: local-docker-testing
description: >-
  Build, deploy, and test the new-api service locally using Docker. Covers
  docker-compose build/start/stop, API testing with valid tokens, channel
  configuration, log inspection, and health checks. Use when the user mentions
  本地测试, docker, 部署, 验证, local test, container, 容器, health check,
  or asks to test code changes locally before deploying to production.
---

# Local Docker Testing

## Prerequisites

- Docker and Docker Compose installed
- Working directory: project root (`e:\new-api` or equivalent)

## Credentials

Read `credentials.local.json` in this skill's directory for all tokens and upstream URLs.

## Quick Start

### Build and Start

```bash
docker compose -f docker-compose.local.yml up -d --build
```

Service runs on **http://localhost:3001** (maps to container port 3000).

### Health Check

```bash
curl -s http://localhost:3001/api/status | python -m json.tool
```

### Stop

```bash
docker compose -f docker-compose.local.yml down
```

## Testing API Requests

Read the token from `credentials.local.json` (`local_docker.tokens.token-0`).

### OpenAI Format

```bash
curl -s -X POST http://localhost:3001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <TOKEN>" \
  -d '{"model":"claude-sonnet-4-6","messages":[{"role":"user","content":"hi"}],"max_tokens":10}'
```

### Claude Native Format

```bash
curl -s -X POST http://localhost:3001/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: <TOKEN>" \
  -H "anthropic-version: 2023-06-01" \
  -d '{"model":"claude-sonnet-4-6","messages":[{"role":"user","content":[{"type":"text","text":"hi"}]}],"max_tokens":10}'
```

## Channel Configuration

Channels sync from DB every 10 seconds. To update a channel:

```bash
docker exec postgres-local psql -U root -d new-api -c "
UPDATE channels SET key='<NEW_KEY>', base_url='<NEW_URL>' WHERE id=<ID>;
"
```

Current channel setup:
- **id=4**: upstream new-api (type=1, OpenAI format), `http://51.81.184.93:31005`
- **id=5**: upstream Claude native (type=14, Anthropic format), same upstream

## Log Inspection

```bash
# Tail logs
docker logs new-api-local --tail 50

# Search for errors
docker logs new-api-local 2>&1 | grep ERR

# Search for specific patterns
docker logs new-api-local 2>&1 | grep "decoding image"
```

## Database Access

```bash
docker exec postgres-local psql -U root -d new-api -c "<SQL>"
```

Common queries:
- List tokens: `SELECT id, key, name, status, remain_quota FROM tokens WHERE status=1;`
- List channels: `SELECT id, name, type, models, base_url, status FROM channels;`
- Check logs: `SELECT * FROM logs ORDER BY id DESC LIMIT 10;`

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| 401 "令牌状态不可用" | Token key wrong or expired | Check `tokens` table, use correct `sk-` prefix |
| 401 from upstream | Upstream channel key invalid | Update channel key in DB, wait 10s for sync |
| Connection refused | Container not running | `docker compose -f docker-compose.local.yml up -d` |
| Build fails | Go compilation error | Check `go build ./...` locally first |
