ALTER TABLE `experiment_bot_events`
  ADD COLUMN `clip_id` bigint unsigned NULL AFTER `brain_version`,
  ADD KEY `idx_experiment_bot_events_clip` (`clip_id`);

ALTER TABLE `experiment_bot_decisions`
  ADD COLUMN `clip_id` bigint unsigned NULL AFTER `brain_version`,
  ADD KEY `idx_experiment_bot_decisions_clip` (`clip_id`);

CREATE TABLE IF NOT EXISTS `experiment_bot_clips` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `experiment_id` bigint unsigned NULL,
  `run_id` bigint unsigned NULL,
  `segment_id` bigint unsigned NULL,
  `bot_guid` int unsigned NOT NULL,
  `trigger_event_id` bigint unsigned NULL,
  `trigger_type` varchar(64) NOT NULL,
  `importance_score` float NOT NULL DEFAULT '0',
  `reason` varchar(128) NOT NULL DEFAULT '',
  `brain_version` varchar(64) NOT NULL DEFAULT '',
  `map_id` int unsigned NOT NULL DEFAULT '0',
  `zone_id` int unsigned NOT NULL DEFAULT '0',
  `area_id` int unsigned NOT NULL DEFAULT '0',
  `x` float NOT NULL DEFAULT '0',
  `y` float NOT NULL DEFAULT '0',
  `z` float NOT NULL DEFAULT '0',
  `started_at` datetime NOT NULL,
  `ended_at` datetime NULL,
  `status` varchar(32) NOT NULL DEFAULT 'open',
  `summary_json` mediumtext NULL,
  PRIMARY KEY (`id`),
  KEY `idx_bot_id` (`bot_guid`, `id`),
  KEY `idx_trigger_id` (`trigger_type`, `id`),
  KEY `idx_segment_id` (`segment_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Triggered autonomous bot telemetry clips';

CREATE TABLE IF NOT EXISTS `experiment_bot_clip_frames` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `clip_id` bigint unsigned NOT NULL,
  `frame_offset_ms` int NOT NULL,
  `bot_guid` int unsigned NOT NULL,
  `map_id` int unsigned NOT NULL,
  `zone_id` int unsigned NOT NULL,
  `area_id` int unsigned NOT NULL,
  `x` float NOT NULL,
  `y` float NOT NULL,
  `z` float NOT NULL,
  `o` float NOT NULL,
  `level` int unsigned NOT NULL,
  `hp_pct` float NOT NULL,
  `power_pct` float NOT NULL,
  `in_combat` tinyint unsigned NOT NULL DEFAULT '0',
  `target_guid` bigint unsigned NOT NULL DEFAULT '0',
  `target_entry` int unsigned NOT NULL DEFAULT '0',
  `quest_id` int unsigned NOT NULL DEFAULT '0',
  `situation_type` varchar(64) NOT NULL DEFAULT '',
  `action` varchar(64) NOT NULL DEFAULT '',
  `raw_json` mediumtext NULL,
  `semantic_json` mediumtext NULL,
  PRIMARY KEY (`id`),
  KEY `idx_clip_frame` (`clip_id`, `id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Pre/post frames for triggered autonomous bot telemetry clips';
