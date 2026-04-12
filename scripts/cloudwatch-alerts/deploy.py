"""
EZModel CloudWatch Alerts — one-click deployment (Python/boto3)

Creates: SNS Topic → Lambda (Telegram notifier) → 12 CloudWatch Alarms

Usage:
    python deploy.py
"""

import io
import json
import time
import zipfile
from pathlib import Path

import boto3
import urllib.request

REGION = "ap-southeast-1"
ACCOUNT_ID = "798831116606"
NAMESPACE = "EZModel/API"

TELEGRAM_BOT_TOKEN = "8506476170:AAHHItVoF0zL_eTgo7Br85aN4gXsbnF5AL0"
TELEGRAM_CHAT_ID = "-4997134369"

SNS_TOPIC_NAME = "EZModel-Alerts"
LAMBDA_NAME = "ezmodel-telegram-notifier"
ROLE_NAME = "ezmodel-telegram-lambda-role"

ECS_CLUSTER = "ezmodel-maas"
ECS_SERVICE = "maas-slave-service-k084m8dy"


def test_telegram():
    """Step 0: Test Telegram Bot connectivity."""
    print("\n>>> Step 0: Testing Telegram Bot connectivity...")
    payload = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": "EZModel Alert Bot deployment starting...",
        "parse_mode": "Markdown",
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
    if resp.get("ok"):
        print(f"    OK  Telegram Bot works, chat_id={TELEGRAM_CHAT_ID}")
    else:
        raise RuntimeError(f"Telegram test failed: {resp}")


def create_sns_topic(sns):
    """Step 1: Create SNS Topic."""
    print("\n>>> Step 1: Creating SNS Topic...")
    resp = sns.create_topic(Name=SNS_TOPIC_NAME)
    arn = resp["TopicArn"]
    print(f"    OK  {arn}")
    return arn


def ensure_iam_role(iam):
    """Step 2: Create IAM Role for Lambda."""
    print("\n>>> Step 2: Ensuring IAM Role...")
    trust_policy = json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"},
            "Action": "sts:AssumeRole",
        }],
    })
    role_arn = f"arn:aws:iam::{ACCOUNT_ID}:role/{ROLE_NAME}"
    try:
        iam.create_role(
            RoleName=ROLE_NAME,
            AssumeRolePolicyDocument=trust_policy,
        )
        print(f"    OK  Created role {ROLE_NAME}")
    except iam.exceptions.EntityAlreadyExistsException:
        print(f"    OK  Role {ROLE_NAME} already exists")

    try:
        iam.attach_role_policy(
            RoleName=ROLE_NAME,
            PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
        )
    except Exception:
        pass

    print("    Waiting 15s for IAM role propagation...")
    time.sleep(15)
    return role_arn


def build_lambda_zip():
    """Build in-memory zip of lambda_telegram.py."""
    source = Path(__file__).parent / "lambda_telegram.py"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(source, "lambda_telegram.py")
    return buf.getvalue()


def deploy_lambda(lam, role_arn):
    """Step 3: Deploy Lambda function."""
    print("\n>>> Step 3: Deploying Lambda function...")
    zip_bytes = build_lambda_zip()
    env = {"Variables": {
        "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "TELEGRAM_CHAT_ID": TELEGRAM_CHAT_ID,
    }}

    try:
        lam.get_function(FunctionName=LAMBDA_NAME)
        print("    Updating existing Lambda...")
        lam.update_function_code(
            FunctionName=LAMBDA_NAME,
            ZipFile=zip_bytes,
        )
        # wait for update to complete before changing config
        time.sleep(5)
        lam.update_function_configuration(
            FunctionName=LAMBDA_NAME,
            Environment=env,
        )
    except lam.exceptions.ResourceNotFoundException:
        print("    Creating new Lambda...")
        lam.create_function(
            FunctionName=LAMBDA_NAME,
            Runtime="python3.12",
            Handler="lambda_telegram.lambda_handler",
            Role=role_arn,
            Code={"ZipFile": zip_bytes},
            Timeout=30,
            MemorySize=128,
            Environment=env,
        )

    arn = f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:{LAMBDA_NAME}"
    print(f"    OK  {arn}")
    return arn


def subscribe_lambda(sns, lam, topic_arn, lambda_arn):
    """Step 4: Subscribe Lambda to SNS Topic."""
    print("\n>>> Step 4: Subscribing Lambda to SNS Topic...")

    try:
        lam.add_permission(
            FunctionName=LAMBDA_NAME,
            StatementId=f"sns-invoke-{int(time.time())}",
            Action="lambda:InvokeFunction",
            Principal="sns.amazonaws.com",
            SourceArn=topic_arn,
        )
    except lam.exceptions.ResourceConflictException:
        pass

    sns.subscribe(
        TopicArn=topic_arn,
        Protocol="lambda",
        Endpoint=lambda_arn,
    )
    print("    OK  Lambda subscribed to SNS")


def create_alarms(cw, topic_arn):
    """Step 5: Create 12 CloudWatch Alarms."""
    print("\n>>> Step 5: Creating CloudWatch Alarms...")

    def put(name, desc, namespace, metric, stat, period, eval_periods,
            threshold, comparison, missing, dimensions=None):
        print(f"    Creating: {name}")
        kwargs = dict(
            AlarmName=name,
            AlarmDescription=desc,
            Namespace=namespace,
            MetricName=metric,
            Statistic=stat,
            Period=period,
            EvaluationPeriods=eval_periods,
            Threshold=threshold,
            ComparisonOperator=comparison,
            TreatMissingData=missing,
            AlarmActions=[topic_arn],
            OKActions=[topic_arn],
        )
        if dimensions:
            kwargs["Dimensions"] = dimensions
        cw.put_metric_alarm(**kwargs)

    ns = NAMESPACE

    # Core channels to monitor (high-traffic channels)
    CORE_CHANNELS = ["ch54", "ch55", "ch58", "ch59"]

    # ── P0: Critical ──────────────────────────────────────────────

    # Per-channel UpstreamErrorCount alarms
    for ch in CORE_CHANNELS:
        ch_dims = [{"Name": "Channel", "Value": ch}]
        put(f"EZModel-P0-UpstreamError-{ch}",
            f"[P0-Critical] {ch} UpstreamErrorCount > 50 in 5min",
            ns, "UpstreamErrorCount", "Sum",
            300, 1, 50, "GreaterThanThreshold", "notBreaching",
            dimensions=ch_dims)

    # Per-channel UpstreamTimeoutCount alarms
    for ch in CORE_CHANNELS:
        ch_dims = [{"Name": "Channel", "Value": ch}]
        put(f"EZModel-P0-UpstreamTimeout-{ch}",
            f"[P0-Critical] {ch} UpstreamTimeoutCount > 30 in 5min",
            ns, "UpstreamTimeoutCount", "Sum",
            300, 1, 30, "GreaterThanThreshold", "notBreaching",
            dimensions=ch_dims)

    # Per-channel BillingFailureCount alarms
    for ch in CORE_CHANNELS:
        ch_dims = [{"Name": "Channel", "Value": ch}]
        put(f"EZModel-P0-BillingFailure-{ch}",
            f"[P0-Critical] {ch} BillingFailureCount > 0",
            ns, "BillingFailureCount", "Sum",
            60, 1, 0, "GreaterThanThreshold", "notBreaching",
            dimensions=ch_dims)

    # ZeroTraffic — use any core channel; if ch54 has zero traffic, service is likely down
    put("EZModel-P0-ZeroTraffic",
        "[P0-Critical] ch54 RequestCount < 1 for 15min — service may be down",
        ns, "RequestCount", "Sum",
        300, 3, 1, "LessThanThreshold", "breaching",
        dimensions=[{"Name": "Channel", "Value": "ch54"}])

    # ── P1: Warning ───────────────────────────────────────────────

    # Pipeline metrics — use "raw_log" pipeline (the primary one)
    pipeline_dims = [{"Name": "Pipeline", "Value": "raw_log"}]

    put("EZModel-P1-LogDrop",
        "[P1-Warning] LogDropCount > 0 (raw_log pipeline)",
        ns, "LogDropCount", "Sum",
        60, 1, 0, "GreaterThanThreshold", "notBreaching",
        dimensions=pipeline_dims)

    put("EZModel-P1-LogUploadFailure",
        "[P1-Warning] LogUploadFailureCount > 0 for 2min (raw_log pipeline)",
        ns, "LogUploadFailureCount", "Sum",
        60, 2, 0, "GreaterThanThreshold", "notBreaching",
        dimensions=pipeline_dims)

    # Per-channel ChannelFallbackCount
    for ch in CORE_CHANNELS:
        ch_dims = [{"Name": "Channel", "Value": ch}]
        put(f"EZModel-P1-ChannelFallback-{ch}",
            f"[P1-Warning] {ch} ChannelFallbackCount > 20 in 5min",
            ns, "ChannelFallbackCount", "Sum",
            300, 1, 20, "GreaterThanThreshold", "notBreaching",
            dimensions=ch_dims)

    # HeapAllocMB — no dimension (RuntimeDims = {{}})
    put("EZModel-P1-MemoryHigh",
        "[P1-Warning] HeapAllocMB > 1500 for 10min",
        ns, "HeapAllocMB", "Maximum",
        300, 2, 1500, "GreaterThanThreshold", "notBreaching")

    # GoroutineCount — no dimension
    put("EZModel-P1-GoroutineLeak",
        "[P1-Warning] GoroutineCount > 5000 for 5min",
        ns, "GoroutineCount", "Maximum",
        300, 1, 5000, "GreaterThanThreshold", "notBreaching")

    # ── P2: Info (ECS infrastructure) ─────────────────────────────

    ecs_dims = [
        {"Name": "ClusterName", "Value": ECS_CLUSTER},
        {"Name": "ServiceName", "Value": ECS_SERVICE},
    ]

    put("EZModel-P2-ECS-CPUHigh",
        "[P2-Info] ECS CPUUtilization > 80%",
        "AWS/ECS", "CPUUtilization", "Average",
        300, 1, 80, "GreaterThanThreshold", "notBreaching",
        dimensions=ecs_dims)

    put("EZModel-P2-ECS-MemoryHigh",
        "[P2-Info] ECS MemoryUtilization > 80%",
        "AWS/ECS", "MemoryUtilization", "Average",
        300, 1, 80, "GreaterThanThreshold", "notBreaching",
        dimensions=ecs_dims)

    put("EZModel-P2-LogQueueDepth",
        "[P2-Info] LogQueueDepth > 5000 (raw_log pipeline)",
        ns, "LogQueueDepth", "Maximum",
        300, 1, 5000, "GreaterThanThreshold", "notBreaching",
        dimensions=[{"Name": "Pipeline", "Value": "raw_log"}])

    # ── NEW: P0 — Upstream 429 throttling spike (per channel) ──

    for ch in CORE_CHANNELS:
        put(f"EZModel-P0-Upstream429-{ch}",
            f"[P0-Critical] {ch} 上游429限流 > 100 in 5min",
            ns, "UpstreamStatusCount", "Sum",
            300, 1, 100, "GreaterThanThreshold", "notBreaching",
            dimensions=[{"Name": "Channel", "Value": ch},
                        {"Name": "StatusGroup", "Value": "4xx_429"}])

    # ── NEW: P0 — Upstream 5xx errors (per channel) ────────────

    for ch in CORE_CHANNELS:
        put(f"EZModel-P0-Upstream5xx-{ch}",
            f"[P0-Critical] {ch} 上游5xx错误 > 30 in 5min",
            ns, "UpstreamStatusCount", "Sum",
            300, 1, 30, "GreaterThanThreshold", "notBreaching",
            dimensions=[{"Name": "Channel", "Value": ch},
                        {"Name": "StatusGroup", "Value": "5xx"}])

    # ── NEW: P0 — Retry exhausted spike ────────────────────────

    put("EZModel-P0-RetryExhausted",
        "[P0-Critical] 重试全部耗尽 > 30 in 5min — 多渠道同时故障",
        ns, "RetryExhaustedCount", "Sum",
        300, 1, 30, "GreaterThanThreshold", "notBreaching")

    # ── NEW: P1 — Channel auto-disabled ────────────────────────

    put("EZModel-P1-ChannelDisabled",
        "[P1-Warning] 渠道被自动禁用",
        ns, "ChannelHealthEventCount", "Sum",
        60, 1, 0, "GreaterThanThreshold", "notBreaching",
        dimensions=[{"Name": "Event", "Value": "auto_disabled"}])

    # ── NEW: P1 — Quota reject spike ──────────────────────────

    put("EZModel-P1-QuotaReject",
        "[P1-Warning] 额度不足拒绝 > 10 in 5min",
        ns, "QuotaRejectCount", "Sum",
        300, 1, 10, "GreaterThanThreshold", "notBreaching")

    # ── NEW: P1 — Rate limit reject spike ─────────────────────

    put("EZModel-P1-RateLimitReject",
        "[P1-Warning] 限流拒绝 > 50 in 5min",
        ns, "RateLimitRejectCount", "Sum",
        300, 1, 50, "GreaterThanThreshold", "notBreaching")

    # ── NEW: P1 — Quota overcharge ─────────────────────────────

    put("EZModel-P1-QuotaOvercharge",
        "[P1-Warning] 配额多扣费 > 20 in 5min",
        ns, "QuotaOverchargeCount", "Sum",
        300, 1, 20, "GreaterThanThreshold", "notBreaching")

    # ── NEW: P2 — Affinity cache miss spike ────────────────────

    put("EZModel-P2-AffinityMiss",
        "[P2-Info] 亲和缓存miss飙升 > 200 in 5min",
        ns, "AffinityMissCount", "Sum",
        300, 1, 200, "GreaterThanThreshold", "notBreaching")

    print("    OK  All alarms created")


def send_completion_notification():
    """Send deployment success message to Telegram."""
    text = (
        "*EZModel CloudWatch Alerts Deployed*\n\n"
        "Alarms created:\n"
        "P0 Critical: billing, upstream errors/timeout/429/5xx, zero traffic, retry exhausted\n"
        "P1 Warning: log drop/upload, fallback, memory, goroutine, channel disabled, quota reject, rate limit, overcharge\n"
        "P2 Info: ECS CPU/memory, log queue, affinity miss\n\n"
        "All alerts will be sent to this group."
    )
    payload = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    urllib.request.urlopen(req, timeout=10)


def main():
    print("=" * 48)
    print("  EZModel CloudWatch Alerts Deployment")
    print("=" * 48)

    test_telegram()

    session = boto3.Session(region_name=REGION)
    sns = session.client("sns")
    iam = session.client("iam")
    lam = session.client("lambda")
    cw = session.client("cloudwatch")

    topic_arn = create_sns_topic(sns)
    role_arn = ensure_iam_role(iam)
    lambda_arn = deploy_lambda(lam, role_arn)
    subscribe_lambda(sns, lam, topic_arn, lambda_arn)

    # Delete old dimensionless alarms that never worked
    print("\n>>> Step 4.5: Cleaning up old dimensionless alarms...")
    OLD_ALARMS = [
        "EZModel-P0-BillingFailure",
        "EZModel-P0-UpstreamErrorSpike",
        "EZModel-P0-UpstreamTimeout",
        "EZModel-P0-ZeroTraffic",
        "EZModel-P1-LogDrop",
        "EZModel-P1-LogUploadFailure",
        "EZModel-P1-ChannelFallback",
        "EZModel-P2-LogQueueDepth",
    ]
    try:
        cw.delete_alarms(AlarmNames=OLD_ALARMS)
        print(f"    Deleted {len(OLD_ALARMS)} old alarms")
    except Exception as e:
        print(f"    Warning: {e}")

    create_alarms(cw, topic_arn)
    send_completion_notification()

    print()
    print("=" * 48)
    print("  Deployment Complete!")
    print("=" * 48)
    print(f"  SNS Topic:  {topic_arn}")
    print(f"  Lambda:     {lambda_arn}")
    print(f"  Alarms:     per-channel + infra alarms created")
    print(f"  Telegram:   {TELEGRAM_CHAT_ID}")
    print()
    print("  To test, run:")
    print("    python deploy.py --test")
    print()


def test_alarm():
    """Manually trigger a test alarm to verify end-to-end."""
    alarm_name = "EZModel-P0-UpstreamError-ch54"
    print(f"Triggering test alarm: {alarm_name} ...")
    cw = boto3.client("cloudwatch", region_name=REGION)
    cw.set_alarm_state(
        AlarmName=alarm_name,
        StateValue="OK",
        StateReason="Reset before test",
    )
    import time; time.sleep(3)
    cw.set_alarm_state(
        AlarmName=alarm_name,
        StateValue="ALARM",
        StateReason="Manual test from deploy.py --test",
    )
    print("Done! Check your Telegram group for the alert.")


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        test_alarm()
    else:
        main()
