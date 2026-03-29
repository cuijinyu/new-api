-- ============================================================
-- Step 4: 创建 Error 日志表（仅非 2xx 请求，与 Raw 同结构）
--
-- S3 路径格式: s3://ezmodel-log/llm-error-logs/2026/03/29/15/xxx.ndjson.gz
-- ============================================================
CREATE EXTERNAL TABLE IF NOT EXISTS ezmodel_logs.error_logs (
  request_id       string    COMMENT '请求唯一标识',
  created_at       string    COMMENT '创建时间 RFC3339 格式',
  method           string    COMMENT 'HTTP 方法',
  path             string    COMMENT '请求路径',
  url              string    COMMENT '上游 URL',
  relay_mode       string    COMMENT '转发模式',
  model            string    COMMENT '模型名称',
  channel_id       int       COMMENT '渠道 ID',
  channel_name     string    COMMENT '渠道名称',
  channel_type     int       COMMENT '渠道类型',
  user_id          int       COMMENT '用户 ID',
  request_headers  string    COMMENT '请求头 JSON（已脱敏）',
  request_body     string    COMMENT '请求体',
  status_code      int       COMMENT 'HTTP 状态码',
  response_body    string    COMMENT '响应体',
  response_error   string    COMMENT '错误信息'
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
LOCATION 's3://ezmodel-log/llm-error-logs/'
TBLPROPERTIES (
  'classification'                        = 'json',
  'compressionType'                       = 'gzip',

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

  'storage.location.template'             = 's3://ezmodel-log/llm-error-logs/${year}/${month}/${day}/${hour}/'
);
