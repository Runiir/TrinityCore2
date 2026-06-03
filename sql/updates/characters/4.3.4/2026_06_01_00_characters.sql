CREATE TABLE IF NOT EXISTS `character_bot_pool` (
  `guid` int unsigned NOT NULL,
  `role` varchar(32) NOT NULL,
  `class_spec` varchar(64) NOT NULL DEFAULT '',
  `enabled` tinyint unsigned NOT NULL DEFAULT '1',
  `in_use` tinyint unsigned NOT NULL DEFAULT '0',
  `experiment_tags` varchar(255) NOT NULL DEFAULT '',
  `notes` varchar(255) NOT NULL DEFAULT '',
  PRIMARY KEY (`guid`),
  KEY `idx_character_bot_pool_role_enabled` (`role`, `enabled`, `in_use`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Reserved player bot character pool';
