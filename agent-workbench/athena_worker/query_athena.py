"""
Athena 查询工具 - 执行 SQL 并打印结果

用法:
    python query_athena.py "SELECT COUNT(*) FROM ezmodel_logs.usage_logs WHERE year='2026' AND month='03'"
    python query_athena.py -f 05_common_queries.sql   # 从文件读取（只执行第一条语句）
"""

import os
import sys
import time
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import boto3

REGION = os.getenv("AWS_REGION", os.getenv("RAW_LOG_S3_REGION", "ap-southeast-1"))
WORKGROUP = os.getenv("ATHENA_WORKGROUP", "primary")
RESULT_BUCKET = os.getenv("ATHENA_RESULT_BUCKET", "ezmodel-log")
RESULT_PREFIX = os.getenv("ATHENA_RESULT_PREFIX", "athena-results")
RESULT_LOCATION = f"s3://{RESULT_BUCKET}/{RESULT_PREFIX}/"

AK = os.getenv("RAW_LOG_S3_ACCESS_KEY_ID", os.getenv("AWS_ACCESS_KEY_ID", ""))
SK = os.getenv("RAW_LOG_S3_SECRET_ACCESS_KEY", os.getenv("AWS_SECRET_ACCESS_KEY", ""))


def get_client():
    kwargs = {"region_name": REGION}
    if AK and SK:
        kwargs["aws_access_key_id"] = AK
        kwargs["aws_secret_access_key"] = SK
    return boto3.client("athena", **kwargs)


def run_and_print(sql: str):
    client = get_client()

    resp = client.start_query_execution(
        QueryString=sql,
        ResultConfiguration={"OutputLocation": RESULT_LOCATION},
        WorkGroup=WORKGROUP,
    )
    exec_id = resp["QueryExecutionId"]

    while True:
        time.sleep(1)
        status = client.get_query_execution(QueryExecutionId=exec_id)
        state = status["QueryExecution"]["Status"]["State"]
        if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break

    if state != "SUCCEEDED":
        reason = status["QueryExecution"]["Status"].get("StateChangeReason", "")
        print(f"查询失败: {state} - {reason}", file=sys.stderr)
        sys.exit(1)

    stats = status["QueryExecution"]["Statistics"]
    scanned_mb = stats.get("DataScannedInBytes", 0) / 1024 / 1024
    exec_ms = stats.get("EngineExecutionTimeInMillis", 0)
    print(f"[扫描 {scanned_mb:.2f} MB, 耗时 {exec_ms} ms]")
    print()

    results = client.get_query_results(QueryExecutionId=exec_id, MaxResults=100)
    rows = results["ResultSet"]["Rows"]
    if not rows:
        print("(无结果)")
        return

    headers = [col["VarCharValue"] for col in rows[0]["Data"]]
    col_widths = [len(h) for h in headers]

    data_rows = []
    for row in rows[1:]:
        vals = [col.get("VarCharValue", "") for col in row["Data"]]
        data_rows.append(vals)
        for i, v in enumerate(vals):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(v))

    fmt = "  ".join(f"{{:<{w}}}" for w in col_widths)
    print(fmt.format(*headers))
    print("  ".join("-" * w for w in col_widths))
    for vals in data_rows:
        while len(vals) < len(headers):
            vals.append("")
        print(fmt.format(*vals))

    total = results["ResultSet"].get("ResultSetMetadata", {})
    if len(rows) > 100:
        print(f"\n... (显示前 99 行)")


def main():
    if len(sys.argv) < 2:
        print("用法: python query_athena.py \"SQL语句\"")
        print("      python query_athena.py -f file.sql")
        sys.exit(1)

    if sys.argv[1] == "-f":
        sql = Path(sys.argv[2]).read_text(encoding="utf-8")
    else:
        sql = " ".join(sys.argv[1:])

    print(f"SQL: {sql[:200]}{'...' if len(sql) > 200 else ''}")
    print()
    run_and_print(sql)


if __name__ == "__main__":
    main()
