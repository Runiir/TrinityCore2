-- Readiness casts on self, but the APL health threshold belongs to the enemy.
ALTER TABLE `bot_rotation_action`
  ADD COLUMN IF NOT EXISTS `max_hostile_target_health_pct` FLOAT NOT NULL DEFAULT 0;

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id` = `action`.`profile_id`
SET `action`.`max_target_health_pct` = 1.00,
    `action`.`max_hostile_target_health_pct` = 0.90
WHERE `profile`.`class_id` = 3
  AND `profile`.`spec_tag` = 'marksmanship'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 23989
  AND `action`.`mechanic_tags` = 'readiness,apl_strict_sequence'
  AND `action`.`target_selector` = 'self';
