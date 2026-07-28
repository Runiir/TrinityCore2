-- Phase 8 Frost Death Knight Masterfrost Killing Machine priority.
--
-- The pinned Masterfrost APL prioritizes Obliterate when Killing Machine is
-- active, then favors Howling Blast through the ordinary rune cycle. Gating the
-- higher-weight Obliterate action on the real 51124 proc preserves both actions
-- without repeating tuning101's all-Howling-Blast rune imbalance.

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`required_self_aura` = 51124,
    `action`.`mechanic_tags` =
      'obliterate,runes,killing_machine,masterfrost'
WHERE `profile`.`class_id` = 6
  AND `profile`.`spec_tag` = 'frost_death_knight'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 49020;
