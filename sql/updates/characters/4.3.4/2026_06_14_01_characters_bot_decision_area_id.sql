ALTER TABLE `experiment_bot_decisions`
  ADD COLUMN `area_id` int unsigned NULL AFTER `zone_id`,
  ADD KEY `idx_experiment_bot_decisions_area` (`area_id`);
