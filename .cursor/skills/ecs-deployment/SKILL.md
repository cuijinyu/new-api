---
name: ecs-deployment
description: >-
  Deploy the new-api service to AWS ECS Fargate. Covers git push to maas
  remote, GitHub Actions image build monitoring, ECS task definition update,
  rolling deployment, and health verification. Use when the user mentions
  部署, deploy, 上线, 发布, ECS, 容器部署, push maas, 推送 maas, rolling update,
  or asks to deploy code changes to production.
---

# ECS Deployment

## Architecture Overview

```
git push maas main
    → GitHub Actions builds Docker image
    → Pushes to Docker Hub + Amazon ECR
    → Agent updates ECS Task Definition with new image
    → ECS rolling deployment (3 tasks)
```

## Key Resources

| Resource | Value |
|----------|-------|
| Git remote | `maas` → `github.com/gallon666/ezmodel.git` |
| GitHub Actions workflow | `.github/workflows/docker-image.yml` |
| Docker Hub image | `docker.io/gallon666/ezmodel:<TAG>` |
| ECR image | `798831116606.dkr.ecr.ap-southeast-1.amazonaws.com/ezmodel/maas:<TAG>` |
| ECS cluster | `ezmodel-maas` |
| ECS service | `maas-slave-service-k084m8dy` |
| Task family | `maas-slave` |
| AWS region | `ap-southeast-1` |

## Deployment Steps

### Step 1: Push to maas remote

```bash
git fetch maas main
git rebase maas/main   # if local is behind remote
git push maas main
```

If push is rejected with "fetch first", run `git fetch maas main && git rebase maas/main` then retry.

若本机 Git 配置了失效代理（如 `127.0.0.1:7897`），可临时关闭再拉推：

```bash
git -c http.proxy= -c https.proxy= fetch maas main
git -c http.proxy= -c https.proxy= push maas main
```

### Step 2: Monitor GitHub Actions build

Requires `gh` CLI authenticated. Add PATH if needed:

```bash
export PATH="$PATH:/c/Program Files/GitHub CLI:/c/Program Files (x86)/GitHub CLI"
```

List recent runs:

```bash
gh api repos/gallon666/ezmodel/actions/runs \
  --jq '.workflow_runs[:3] | .[] | "\(.id) \(.status) \(.conclusion // "running...") \(.display_title) \(.created_at)"'
```

Poll a specific run until `completed success`:

```bash
gh api repos/gallon666/ezmodel/actions/runs/<RUN_ID> \
  --jq '"\(.status) \(.conclusion // "running...")"'
```

Get the image tag from build logs:

```bash
gh run view <RUN_ID> --repo gallon666/ezmodel --log 2>&1 | rg "Amazon ECR:"
```

The tag format is `YYYYMMDDHHmmss` (Asia/Shanghai timezone). Build typically takes 4-6 minutes.

### Step 3: Update ECS Task Definition and deploy

Use Python with boto3. The script:
1. Describes the current service to get the active task definition
2. Copies all settings from the current task definition
3. Updates the container image to the new ECR image
4. Registers a new task definition revision
5. Updates the service with `forceNewDeployment=True`

```python
import boto3

ecs = boto3.client('ecs', region_name='ap-southeast-1')
NEW_IMAGE = "798831116606.dkr.ecr.ap-southeast-1.amazonaws.com/ezmodel/maas:<TAG>"

# Get current task definition
svc = ecs.describe_services(cluster='ezmodel-maas', services=['maas-slave-service-k084m8dy'])['services'][0]
td = ecs.describe_task_definition(taskDefinition=svc['taskDefinition'])['taskDefinition']

# Build register params (copy from current)
params = {
    'family': td['family'],
    'containerDefinitions': td['containerDefinitions'],
    'volumes': td.get('volumes', []),
    'placementConstraints': td.get('placementConstraints', []),
}
for key in ['taskRoleArn', 'executionRoleArn', 'networkMode', 'requiresCompatibilities', 'cpu', 'memory', 'runtimePlatform']:
    if td.get(key):
        params[key] = td[key]

# Update image
for c in params['containerDefinitions']:
    if 'maas' in c['name'].lower():
        c['image'] = NEW_IMAGE

# Register and deploy
new_td = ecs.register_task_definition(**params)['taskDefinition']
ecs.update_service(
    cluster='ezmodel-maas',
    service='maas-slave-service-k084m8dy',
    taskDefinition=new_td['taskDefinitionArn'],
    forceNewDeployment=True
)
```

### Step 4: Monitor rolling deployment

Poll until PRIMARY deployment shows `desired == running` and old deployment drains:

```python
svc = ecs.describe_services(cluster='ezmodel-maas', services=['maas-slave-service-k084m8dy'])['services'][0]
for d in svc['deployments']:
    print(f"{d['status']}: td={d['taskDefinition'].split('/')[-1]}, "
          f"desired={d['desiredCount']}, running={d['runningCount']}, "
          f"rollout={d.get('rolloutState','N/A')}")
```

Typical rollout takes 2-4 minutes. Poll every 30-60 seconds.

## AWS Credentials

Read from environment or use the credentials stored in the local-docker-testing skill's `credentials.local.json`. The IAM user needs permissions for:
- `ecs:DescribeServices`, `ecs:UpdateService`
- `ecs:DescribeTaskDefinition`, `ecs:RegisterTaskDefinition`

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `git push` rejected | Remote has commits you don't have | `git fetch maas main && git rebase maas/main` |
| Actions build fails | Go compilation error or Docker build issue | Check `gh run view <ID> --repo gallon666/ezmodel --log` |
| ECS tasks fail to start | Bad env vars or image issue | Check CloudWatch logs at `/ecs/maas-slave` |
| Rollout stuck | Health check failing | Inspect ALB target group health and container logs |
| `gh` not found | PATH not set | `export PATH="$PATH:/c/Program Files/GitHub CLI"` |
| `git fetch` SSL / network errors | Unstable network or proxy | Retry; disable broken `http(s).proxy` for Git |
