-- Roll back only with a native loader that no longer selects this column.
ALTER TABLE `bot_rotation_action`
  DROP COLUMN IF EXISTS `min_hostile_target_health_pct`;
