-- The raid telemetry context contains the complete admission/runtime and
-- mechanic evidence. Keep it lossless as the structured diagnostic payload
-- grows; MEDIUMTEXT also matches canonical_event_json's storage contract.
ALTER TABLE `experiment_bot_events`
  MODIFY COLUMN `context_json` mediumtext NULL;
