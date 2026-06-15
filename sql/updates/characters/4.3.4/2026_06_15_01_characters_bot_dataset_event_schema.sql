ALTER TABLE `experiment_bot_events`
  ADD COLUMN `schema_version` varchar(32) NOT NULL DEFAULT 'bot_dataset_event_v1' AFTER `id`,
  ADD COLUMN `feature_schema_version` varchar(64) NOT NULL DEFAULT 'bot_policy_features_v1' AFTER `schema_version`,
  ADD COLUMN `canonical_event_json` mediumtext NULL AFTER `context_json`;

ALTER TABLE `experiment_bot_decisions`
  ADD COLUMN `schema_version` varchar(32) NOT NULL DEFAULT 'bot_dataset_event_v1' AFTER `id`,
  ADD COLUMN `canonical_event_json` mediumtext NULL AFTER `outcome_json`;

ALTER TABLE `experiment_bot_replay_records`
  ADD COLUMN `schema_version` varchar(32) NOT NULL DEFAULT 'bot_dataset_event_v1' AFTER `id`,
  ADD COLUMN `feature_schema_version` varchar(64) NOT NULL DEFAULT 'bot_policy_features_v1' AFTER `schema_version`,
  ADD COLUMN `canonical_event_json` mediumtext NULL AFTER `failure_json`;

ALTER TABLE `experiment_bot_clips`
  ADD COLUMN `schema_version` varchar(32) NOT NULL DEFAULT 'bot_dataset_event_v1' AFTER `id`,
  ADD COLUMN `feature_schema_version` varchar(64) NOT NULL DEFAULT 'bot_policy_features_v1' AFTER `schema_version`,
  ADD COLUMN `canonical_event_json` mediumtext NULL AFTER `summary_json`;

ALTER TABLE `experiment_bot_clip_frames`
  ADD COLUMN `schema_version` varchar(32) NOT NULL DEFAULT 'bot_dataset_event_v1' AFTER `id`,
  ADD COLUMN `feature_schema_version` varchar(64) NOT NULL DEFAULT 'bot_policy_features_v1' AFTER `schema_version`,
  ADD COLUMN `canonical_event_json` mediumtext NULL AFTER `semantic_json`;
