CREATE TABLE IF NOT EXISTS `bot_memory_danger_zones` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `bot_guid` int unsigned NOT NULL,
  `map_id` int unsigned NOT NULL,
  `zone_id` int unsigned NOT NULL,
  `area_id` int unsigned NOT NULL,
  `x` float NOT NULL,
  `y` float NOT NULL,
  `z` float NOT NULL,
  `radius` float NOT NULL,
  `danger_type` varchar(64) NOT NULL,
  `source_entry` int unsigned NOT NULL DEFAULT '0',
  `death_count` int unsigned NOT NULL DEFAULT '0',
  `stuck_count` int unsigned NOT NULL DEFAULT '0',
  `failure_count` int unsigned NOT NULL DEFAULT '0',
  `last_event_at` datetime NOT NULL,
  `metadata_json` mediumtext NULL,
  PRIMARY KEY (`id`),
  KEY `idx_bot_zone` (`bot_guid`, `map_id`, `zone_id`),
  KEY `idx_danger_type` (`danger_type`, `source_entry`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `bot_memory_safe_positions` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `bot_guid` int unsigned NOT NULL,
  `map_id` int unsigned NOT NULL,
  `zone_id` int unsigned NOT NULL,
  `area_id` int unsigned NOT NULL,
  `x` float NOT NULL,
  `y` float NOT NULL,
  `z` float NOT NULL,
  `o` float NOT NULL,
  `hp_pct` float NOT NULL,
  `last_seen_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_bot_recent` (`bot_guid`, `last_seen_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
