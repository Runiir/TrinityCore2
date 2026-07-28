-- Phase 8 Demonology Warlock Hellfire survival correction.
--
-- The solo calibration lane must execute the real Hellfire self-damage path.
-- Begin another channel only from a safe health reserve and prioritize the
-- existing Drain Life recovery action until that reserve is restored. This
-- preserves the pinned offensive action while preventing one accepted AoE
-- window from persisting a dead character into the next seed.

UPDATE `bot_rotation_action` AS `action`
INNER JOIN `bot_rotation_profile` AS `profile`
    ON `profile`.`id` = `action`.`profile_id`
SET `action`.`min_self_health_pct` = 0.90
WHERE `profile`.`class_id` = 9
  AND `profile`.`spec_tag` = 'demonology_warlock'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 1949;

UPDATE `bot_rotation_action` AS `action`
INNER JOIN `bot_rotation_profile` AS `profile`
    ON `profile`.`id` = `action`.`profile_id`
SET `action`.`max_self_health_pct` = 0.90
WHERE `profile`.`class_id` = 9
  AND `profile`.`spec_tag` = 'demonology_warlock'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 689;

UPDATE `bot_rotation_profile`
SET `version` = IF(
        `source_note` = 'phase8_demonology_hellfire_survival_2026_07_27',
        `version`,
        `version` + 1
    ),
    `source_note` = 'phase8_demonology_hellfire_survival_2026_07_27',
    `scope_note` = 'Phase 8 Demonology real-Hellfire solo survival correction'
WHERE `class_id` = 9
  AND `spec_tag` = 'demonology_warlock'
  AND `role` = 'dps';
