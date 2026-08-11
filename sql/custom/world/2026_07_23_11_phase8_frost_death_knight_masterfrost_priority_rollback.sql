-- Phase 8 Frost Death Knight Masterfrost priority rollback.
--
-- Weighting Howling Blast above Obliterate eliminated Obliterate entirely and
-- converted unmatched Unholy runes into excessive Plague Strikes. Restore the
-- tuning100 action balance while preserving single-target Howling Blast.

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`damage_weight` = 0.92,
    `action`.`mechanic_tags` =
      'howling_blast,frost_fever,masterfrost,single_target,aoe'
WHERE `profile`.`class_id` = 6
  AND `profile`.`spec_tag` = 'frost_death_knight'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 49184;
