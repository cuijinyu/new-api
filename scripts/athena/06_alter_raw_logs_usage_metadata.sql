-- Add tail and usage metadata fields for large raw log responses.
-- Existing raw log objects remain readable; new objects can expose these fields
-- after this ALTER is applied to the Athena table.

ALTER TABLE ezmodel_logs.raw_logs ADD COLUMNS (
  response_body_tail string COMMENT 'response body tail fragment for truncated large responses',
  response_body_bytes bigint COMMENT 'original response body byte count',
  response_body_truncated boolean COMMENT 'whether response_body was truncated',
  response_usage_metadata string COMMENT 'Gemini usageMetadata JSON captured separately'
);
