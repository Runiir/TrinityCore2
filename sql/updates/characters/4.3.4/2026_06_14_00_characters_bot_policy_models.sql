CREATE TABLE IF NOT EXISTS `bot_policy_models` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `model_version` varchar(128) NOT NULL,
  `model_type` varchar(64) NOT NULL,
  `backend` varchar(64) NOT NULL DEFAULT '',
  `git_commit` varchar(64) NOT NULL DEFAULT '',
  `dataset_path` text NOT NULL,
  `artifact_path` text NOT NULL,
  `feature_schema_json` mediumtext NOT NULL,
  `label_schema_json` mediumtext NOT NULL,
  `train_run_ids` mediumtext NOT NULL,
  `eval_run_ids` mediumtext NOT NULL,
  `metrics_json` mediumtext NULL,
  `diagnostics_json` mediumtext NULL,
  `accepted` tinyint unsigned NOT NULL DEFAULT '0',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uniq_bot_policy_models_version` (`model_version`),
  KEY `idx_bot_policy_models_accepted` (`accepted`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Offline-trained autonomous bot policy model registry';

CREATE TABLE IF NOT EXISTS `bot_policy_evaluations` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `model_version` varchar(128) NOT NULL,
  `model_type` varchar(64) NOT NULL,
  `backend` varchar(64) NOT NULL DEFAULT '',
  `git_commit` varchar(64) NOT NULL DEFAULT '',
  `dataset_path` text NOT NULL,
  `artifact_path` text NOT NULL,
  `feature_schema_json` mediumtext NOT NULL,
  `label_schema_json` mediumtext NOT NULL,
  `train_run_ids` mediumtext NOT NULL,
  `eval_run_ids` mediumtext NOT NULL,
  `metrics_json` mediumtext NOT NULL,
  `diagnostics_json` mediumtext NOT NULL,
  `accepted` tinyint unsigned NOT NULL DEFAULT '0',
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_bot_policy_evaluations_model` (`model_version`, `created_at`),
  KEY `idx_bot_policy_evaluations_accepted` (`accepted`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Held-out autonomous bot policy model evaluations';

ALTER TABLE `experiment_bot_decisions`
  ADD COLUMN `model_version` varchar(128) NULL AFTER `brain_version`,
  ADD COLUMN `feature_schema_version` varchar(64) NULL AFTER `model_version`,
  ADD COLUMN `model_score` float NULL AFTER `feature_schema_version`,
  ADD COLUMN `model_rank` int unsigned NULL AFTER `model_score`,
  ADD COLUMN `model_features_hash` int unsigned NULL AFTER `model_rank`,
  ADD KEY `idx_experiment_bot_decisions_model` (`model_version`, `run_id`),
  ADD KEY `idx_experiment_bot_decisions_model_rank` (`model_version`, `model_rank`);
