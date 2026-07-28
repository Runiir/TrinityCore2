-- Phase 8 Frost Death Knight Killing Machine experiment rollback.
--
-- Static aura reservation increased Obliterate use but suppressed the ordinary
-- Masterfrost rune cycle, causing long no-valid-action waits and severe resource
-- capping. Restore the tuning100 action gates while preserving its successful
-- single-target Howling Blast tuning.

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`required_self_aura` = 0,
    `action`.`forbidden_self_aura` = 0,
    `action`.`mechanic_tags` = 'obliterate,runes'
WHERE `profile`.`class_id` = 6
  AND `profile`.`spec_tag` = 'frost_death_knight'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 49020;

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`forbidden_self_aura` = 0
WHERE `profile`.`class_id` = 6
  AND `profile`.`spec_tag` = 'frost_death_knight'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 49143;

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`damage_weight` = 0.92,
    `action`.`min_enemies` = 1,
    `action`.`required_self_aura` = 0,
    `action`.`forbidden_self_aura` = 0,
    `action`.`mechanic_tags` =
      'howling_blast,frost_fever,masterfrost,single_target,aoe'
WHERE `profile`.`class_id` = 6
  AND `profile`.`spec_tag` = 'frost_death_knight'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 49184;
