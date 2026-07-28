-- Phase 8 Retribution Paladin melee-lane correction.
--
-- Hammer of Wrath has no hostile minimum range in Cataclysm. Marking it as a
-- ranged-only action made its otherwise normal execute/Avenging Wrath rejection
-- request a synthetic five-yard minimum. When no other action was ready, that
-- leaked into the melee fallback and produced repeated movement/range-loss ticks.

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`requires_ranged_range` = 0,
    a.`min_range` = 0,
    a.`max_range` = 30,
    a.`movement_directive` = 'melee',
    a.`auto_attack_mode` = 'melee'
WHERE p.`class_id` = 2
  AND p.`spec_tag` = 'retribution_paladin'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 24275;

UPDATE `bot_rotation_profile`
SET `version` = IF(
        `source_note` = 'phase8_retribution_hammer_range_2026_07_27',
        `version`,
        `version` + 1
    ),
    `source_note` = 'phase8_retribution_hammer_range_2026_07_27',
    `scope_note` = 'Phase 8 Retribution Hammer of Wrath melee-lane correction'
WHERE `class_id` = 2
  AND `spec_tag` = 'retribution_paladin'
  AND `role` = 'dps';
