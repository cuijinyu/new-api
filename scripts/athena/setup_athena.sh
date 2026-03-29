#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Athena 一键建表脚本
# 在 S3 上的 ndjson.gz 日志之上创建 Athena 外部表
# ============================================================

REGION="${AWS_REGION:-ap-southeast-1}"
WORKGROUP="${ATHENA_WORKGROUP:-primary}"
RESULT_BUCKET="${ATHENA_RESULT_BUCKET:-ezmodel-log}"
RESULT_PREFIX="${ATHENA_RESULT_PREFIX:-athena-results}"
RESULT_LOCATION="s3://${RESULT_BUCKET}/${RESULT_PREFIX}/"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

run_query() {
    local sql_file="$1"
    local description="$2"
    echo ">>> ${description} (${sql_file})"

    local sql
    sql=$(<"${SCRIPT_DIR}/${sql_file}")

    local exec_id
    exec_id=$(aws athena start-query-execution \
        --query-string "${sql}" \
        --result-configuration "OutputLocation=${RESULT_LOCATION}" \
        --work-group "${WORKGROUP}" \
        --region "${REGION}" \
        --output text --query 'QueryExecutionId')

    echo "    QueryExecutionId: ${exec_id}"

    local state="RUNNING"
    while [[ "${state}" == "RUNNING" || "${state}" == "QUEUED" ]]; do
        sleep 2
        state=$(aws athena get-query-execution \
            --query-execution-id "${exec_id}" \
            --region "${REGION}" \
            --output text --query 'QueryExecution.Status.State')
    done

    if [[ "${state}" == "SUCCEEDED" ]]; then
        echo "    ✓ ${description} 成功"
    else
        local reason
        reason=$(aws athena get-query-execution \
            --query-execution-id "${exec_id}" \
            --region "${REGION}" \
            --output text --query 'QueryExecution.Status.StateChangeReason' 2>/dev/null || echo "unknown")
        echo "    ✗ ${description} 失败: state=${state}, reason=${reason}"
        exit 1
    fi
    echo ""
}

echo "============================================"
echo "  Athena 建表 - EZModel 日志分析"
echo "  Region: ${REGION}"
echo "  Workgroup: ${WORKGROUP}"
echo "  Result Location: ${RESULT_LOCATION}"
echo "============================================"
echo ""

run_query "01_create_database.sql"          "创建数据库 ezmodel_logs"
run_query "02_create_usage_logs_table.sql"   "创建 usage_logs 表"
run_query "03_create_raw_logs_table.sql"     "创建 raw_logs 表"
run_query "04_create_error_logs_table.sql"   "创建 error_logs 表"

echo "============================================"
echo "  全部完成！"
echo ""
echo "  现在可以在 Athena 控制台或 CLI 中查询："
echo "    SELECT COUNT(*) FROM ezmodel_logs.usage_logs"
echo "    WHERE year='2026' AND month='03' AND day='29';"
echo ""
echo "  更多查询示例见: 05_common_queries.sql"
echo "============================================"
