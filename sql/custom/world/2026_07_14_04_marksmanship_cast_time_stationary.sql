-- Aimed Shot and Steady Shot have cast times in the Cataclysm marksman kit.
-- Mask them while moving so mobile mechanic phases fall through to instant shots.
UPDATE `bot_rotation_action` AS `action`
INNER JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id` = `action`.`profile_id`
SET `action`.`requires_stationary` = 1
WHERE `profile`.`class_id` = 3
  AND `profile`.`spec_tag` = 'marksmanship'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` IN (19434, 56641);
