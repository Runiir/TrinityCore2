ALTER TABLE `experiment_bot_decisions`
  ADD KEY `idx_experiment_bot_decisions_bot_ts_failure` (`bot_guid`, `ts`, `is_failure`);

ALTER TABLE `experiment_bot_replay_records`
  ADD KEY `idx_experiment_bot_replay_records_bot_created_type_zone` (`bot_guid`, `created_at`, `replay_type`, `zone_id`);

ALTER TABLE `experiment_bot_clips`
  ADD KEY `idx_experiment_bot_clips_bot_started_area_zone_trigger_status` (`bot_guid`, `started_at`, `area_id`, `zone_id`, `trigger_type`, `status`);

ALTER TABLE `experiment_bot_segments`
  ADD KEY `idx_experiment_bot_segments_bot_started_status_name_area_zone` (`bot_guid`, `started_at`, `status`, `experiment_name`, `area_id`, `zone_id`);

ALTER TABLE `bot_memory_failed_paths`
  ADD KEY `idx_bot_memory_failed_paths_bot_map_last_failed` (`bot_guid`, `map_id`, `last_failed_at`);
