-- ============================================================
-- Step 2: 创建 Usage 日志表（核心账务表，用于出账单和费用分析）
--
-- S3 路径格式: s3://ezmodel-log/llm-usage-logs/2026/03/29/15/xxx.ndjson.gz
-- 使用 Partition Projection 自动推断分区，无需手动 MSCK REPAIR
-- ============================================================
CREATE EXTERNAL TABLE IF NOT EXISTS ezmodel_logs.usage_logs (
  request_id        string    COMMENT '请求唯一标识',
  created_at        bigint    COMMENT '创建时间 Unix 时间戳（秒）',
  user_id           int       COMMENT '用户 ID',
  username          string    COMMENT '用户名',
  channel_id        int       COMMENT '渠道 ID',
  model_name        string    COMMENT '模型名称',
  token_name        string    COMMENT 'API Token 名称',
  token_id          int       COMMENT 'API Token ID',
  `group`           string    COMMENT '用户分组',
  prompt_tokens     int       COMMENT '输入 tokens 数',
  completion_tokens int       COMMENT '输出 tokens 数',
  quota             int       COMMENT '消耗额度（内部单位，÷500000=USD）',
  content           string    COMMENT '请求内容摘要',
  use_time_seconds  int       COMMENT '请求耗时（秒）',
  is_stream         boolean   COMMENT '是否流式请求',
  ip                string    COMMENT '客户端 IP',
  other             string    COMMENT '扩展字段 JSON（含 frt, cache_tokens, web_search 等）'
)
PARTITIONED BY (
  `year`  string,
  `month` string,
  `day`   string,
  `hour`  string
)
ROW FORMAT SERDE 'org.openx.data.jsonserde.JsonSerDe'
WITH SERDEPROPERTIES (
  'ignore.malformed.json' = 'TRUE',
  'case.insensitive'      = 'TRUE'
)
STORED AS INPUTFORMAT  'org.apache.hadoop.mapred.TextInputFormat'
OUTPUTFORMAT 'org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat'
LOCATION 's3://ezmodel-log/llm-usage-logs/'
TBLPROPERTIES (
  'classification'                        = 'json',
  'compressionType'                       = 'gzip',

  -- Partition Projection: 自动按路径推断分区，无需 MSCK REPAIR TABLE
  'projection.enabled'                    = 'true',

  'projection.year.type'                  = 'integer',
  'projection.year.range'                 = '2024,2030',

  'projection.month.type'                 = 'integer',
  'projection.month.range'                = '1,12',
  'projection.month.digits'              = '2',

  'projection.day.type'                   = 'integer',
  'projection.day.range'                  = '1,31',
  'projection.day.digits'                = '2',

  'projection.hour.type'                  = 'integer',
  'projection.hour.range'                 = '0,23',
  'projection.hour.digits'               = '2',

  'storage.location.template'             = 's3://ezmodel-log/llm-usage-logs/${year}/${month}/${day}/${hour}/'
);
