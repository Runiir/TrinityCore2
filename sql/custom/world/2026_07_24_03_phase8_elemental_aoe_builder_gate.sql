-- Chain Lightning replaces Lightning Bolt as Elemental's filler when multiple
-- targets are present. Mark Lightning Bolt as single-target-only so AoE runtime
-- coverage does not require a builder that density selection cannot execute.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id` = `action`.`profile_id`
SET `action`.`max_enemies` = 1
WHERE `profile`.`class_id` = 7
  AND `profile`.`spec_tag` = 'elemental_shaman'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 403;
