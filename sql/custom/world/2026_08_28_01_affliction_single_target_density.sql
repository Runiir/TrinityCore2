-- Affliction's WoWSims-aligned actions are single-target actions.  Nearby
-- Magmaw parasites must not make their max_enemies=1 rows ineligible; native
-- spell legality and encounter area-damage guards remain authoritative.
-- Re-running this migration is safe because it only assigns the same values.

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 5),
    `source_note` = 'wowsims_affliction_single_target_density_v1'
WHERE `class_id` = 9
  AND `spec_tag` = 'affliction_warlock'
  AND `role` = 'dps';

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`max_enemies` = 0
WHERE `profile`.`class_id` = 9
  AND `profile`.`spec_tag` = 'affliction_warlock'
  AND `profile`.`role` = 'dps'
  AND `action`.`category` NOT IN ('aoe', 'cleave')
  AND `action`.`spell_id` IN (603, 172, 30108, 48181, 6353, 1120, 77799,
      47897, 686);
