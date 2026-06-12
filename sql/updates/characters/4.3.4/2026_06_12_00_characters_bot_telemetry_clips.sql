ALTER TABLE `experiment_bot_events`
  ADD COLUMN `clip_id` bigint unsigned NULL AFTER `brain_version`,
  ADD KEY `idx_experiment_bot_events_clip` (`clip_id`);

ALTER TABLE `experiment_bot_decisions`
  ADD COLUMN `clip_id` bigint unsigned NULL AFTER `brain_version`,
  ADD KEY `idx_experiment_bot_decisions_clip` (`clip_id`);

CREATE TABLE IF NOT EXISTS `experiment_bot_telemetry_clips` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `experiment_id` bigint unsigned NOT NULL,
  `run_id` bigint unsigned NOT NULL,
  `bot_guid` int unsigned NOT NULL,
  `brain_version` varchar(64) NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `trigger_type` varchar(64) NOT NULL,
  `importance_score` float NOT NULL DEFAULT '0',
  `start_time_ms` bigint unsigned NOT NULL,
  `end_time_ms` bigint unsigned NOT NULL,
  `pre_frame_count` int unsigned NOT NULL DEFAULT '0',
  `post_frame_count` int unsigned NOT NULL DEFAULT '0',
  `summary_json` text NULL,
  `status` varchar(16) NOT NULL DEFAULT 'open',
  PRIMARY KEY (`id`),
  KEY `idx_experiment_bot_telemetry_clips_run_bot` (`run_id`, `bot_guid`),
  KEY `idx_experiment_bot_telemetry_clips_trigger` (`trigger_type`),
  KEY `idx_experiment_bot_telemetry_clips_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Triggered autonomous bot telemetry clips';

CREATE TABLE IF NOT EXISTS `experiment_bot_telemetry_frames` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `experiment_id` bigint unsigned NOT NULL,
  `run_id` bigint unsigned NOT NULL,
  `clip_id` bigint unsigned NOT NULL,
  `bot_guid` int unsigned NOT NULL,
  `frame_phase` varchar(8) NOT NULL,
  `frame_index` int unsigned NOT NULL,
  `timestamp_ms` bigint unsigned NOT NULL,
  `map_id` int unsigned NULL,
  `zone_id` int unsigned NULL,
  `area_id` int unsigned NULL,
  `x` float NULL,
  `y` float NULL,
  `z` float NULL,
  `o` float NULL,
  `level` tinyint unsigned NULL,
  `hp_pct` float NULL,
  `power_pct` float NULL,
  `in_combat` tinyint unsigned NOT NULL DEFAULT '0',
  `target_guid` bigint unsigned NULL,
  `target_entry` int unsigned NULL,
  `quest_id` int unsigned NULL,
  `situation_type` varchar(64) NULL,
  `action` varchar(64) NULL,
  `raw_json` text NULL,
  `semantic_json` text NULL,
  PRIMARY KEY (`id`),
  KEY `idx_experiment_bot_telemetry_frames_clip` (`clip_id`, `frame_phase`, `frame_index`),
  KEY `idx_experiment_bot_telemetry_frames_run_bot` (`run_id`, `bot_guid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Pre/post frames for triggered autonomous bot telemetry clips';
