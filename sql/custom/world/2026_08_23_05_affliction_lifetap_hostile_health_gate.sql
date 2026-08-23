-- Keep self-targeted Affliction Life Tap out of the WoWSims execute phase.
-- The typed gate is an exclusive lower bound: the hostile target must be
-- strictly above 25% health before Life Tap is eligible.

ALTER TABLE `bot_rotation_action`
  ADD COLUMN IF NOT EXISTS `min_hostile_target_health_pct` FLOAT NOT NULL DEFAULT 0
    AFTER `requires_ground_target`;

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`min_hostile_target_health_pct` = 0.25
WHERE `profile`.`class_id` = 9
  AND `profile`.`spec_tag` = 'affliction_warlock'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 1454;
