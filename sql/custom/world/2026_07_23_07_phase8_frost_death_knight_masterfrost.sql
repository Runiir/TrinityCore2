-- Phase 8 Frost Death Knight single-target qualification tuning.
--
-- The canonical dual-wield Masterfrost profile must spend standalone Frost
-- runes with Howling Blast in single-target combat. Restricting the action to
-- two enemies strands Frost and Unholy runes after Plague Strike and leaves
-- repeated no-valid-action decisions between Obliterate windows.

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`min_enemies` = 1,
    `action`.`mechanic_tags` = 'howling_blast,frost_fever,masterfrost,single_target,aoe'
WHERE `profile`.`class_id` = 6
  AND `profile`.`spec_tag` = 'frost_death_knight'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 49184;
