"""
Athena 一键建表脚本（Python 版）
在 S3 上的 ndjson.gz 日志之上创建 Athena 外部表

用法:
    cd scripts/athena
    python setup_athena.py

环境变量（可选）:
    AWS_REGION              默认 ap-southeast-1
    ATHENA_WORKGROUP        默认 primary
    ATHENA_RESULT_BUCKET    默认 ezmodel-log
    ATHENA_RESULT_PREFIX    默认 athena-results
    RAW_LOG_S3_ACCESS_KEY_ID / AWS_ACCESS_KEY_ID
    RAW_LOG_S3_SECRET_ACCESS_KEY / AWS_SECRET_ACCESS_KEY
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

SCRIPT_DIR = Path(__file__).resolve().parent

SQL_FILES = [
    ("01_create_database.sql",        "创建数据库 ezmodel_logs"),
    ("02_create_usage_logs_table.sql", "创建 usage_logs 表"),
    ("03_create_raw_logs_table.sql",   "创建 raw_logs 表"),
    ("04_create_error_logs_table.sql", "创建 error_logs 表"),
]


def get_athena_client():
    kwargs = {"region_name": REGION}
    if AK and SK:
        kwargs["aws_access_key_id"] = AK
        kwargs["aws_secret_access_key"] = SK
    return boto3.client("athena", **kwargs)


def run_query(client, sql_file: str, description: str):
    sql_path = SCRIPT_DIR / sql_file
    sql = sql_path.read_text(encoding="utf-8")

    print(f">>> {description} ({sql_file})")

    resp = client.start_query_execution(
        QueryString=sql,
        ResultConfiguration={"OutputLocation": RESULT_LOCATION},
        WorkGroup=WORKGROUP,
    )
    exec_id = resp["QueryExecutionId"]
    print(f"    QueryExecutionId: {exec_id}")

    while True:
        time.sleep(2)
        status = client.get_query_execution(QueryExecutionId=exec_id)
        state = status["QueryExecution"]["Status"]["State"]
        if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break

    if state == "SUCCEEDED":
        print(f"    ✓ {description} 成功")
    else:
        reason = status["QueryExecution"]["Status"].get("StateChangeReason", "unknown")
        print(f"    ✗ {description} 失败: state={state}, reason={reason}")
        sys.exit(1)
    print()


def main():
    print("=" * 50)
    print("  Athena 建表 - EZModel 日志分析")
    print(f"  Region: {REGION}")
    print(f"  Workgroup: {WORKGROUP}")
    print(f"  Result Location: {RESULT_LOCATION}")
    print("=" * 50)
    print()

    client = get_athena_client()

    for sql_file, desc in SQL_FILES:
        run_query(client, sql_file, desc)

    print("=" * 50)
    print("  全部完成！")
    print()
    print("  现在可以在 Athena 控制台或 CLI 中查询：")
    print("    SELECT COUNT(*) FROM ezmodel_logs.usage_logs")
    print("    WHERE year='2026' AND month='03' AND day='29';")
    print()
    print("  更多查询示例见: 05_common_queries.sql")
    print("=" * 50)


if __name__ == "__main__":
    main()
