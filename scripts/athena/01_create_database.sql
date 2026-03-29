-- ============================================================
-- Step 1: 创建 Athena 数据库
-- ============================================================
CREATE DATABASE IF NOT EXISTS ezmodel_logs
  COMMENT 'EZModel LLM API 日志分析数据仓库'
  LOCATION 's3://ezmodel-log/';
