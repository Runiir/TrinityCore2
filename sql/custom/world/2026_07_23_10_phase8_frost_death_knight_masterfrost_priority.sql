-- Phase 8 Frost Death Knight Masterfrost action-priority tuning.
--
-- Runtime role scoring doubles damage_weight inside the selected priority
-- bucket. Give Howling Blast the intended Masterfrost priority over Obliterate
-- when both actions are valid; sort_order alone cannot override the score.

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`damage_weight` = 1.00,
    `action`.`mechanic_tags` = 'howling_blast,frost_fever,masterfrost,single_target,aoe,primary'
WHERE `profile`.`class_id` = 6
  AND `profile`.`spec_tag` = 'frost_death_knight'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 49184;
