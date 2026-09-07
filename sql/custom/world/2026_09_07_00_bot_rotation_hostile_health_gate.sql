-- Match BotClassSpecActionProfileDb's native SELECT and disabled-by-default gate.
ALTER TABLE `bot_rotation_action`
  ADD COLUMN IF NOT EXISTS `min_hostile_target_health_pct` FLOAT NOT NULL DEFAULT 0;
