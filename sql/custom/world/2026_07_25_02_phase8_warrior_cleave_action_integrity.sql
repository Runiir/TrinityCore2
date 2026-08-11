-- Phase 8 Warrior Cleave action-integrity correction.
-- Representative-final r6 Arms AoE evidence showed Cleave selected 26 times
-- and accepted without cast failures, but its 78 damage events produced only
-- 103 total damage. Protection Warrior evidence had already shown the same
-- effectively broken behavior. Remove Cleave from every Warrior profile while
-- preserving the healthy Arms AoE cycle: Thunder Clap, Sweeping Strikes, and
-- Bladestorm. The unchanged performance and runtime-integrity gates remain
-- authoritative.

DELETE a FROM `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
WHERE p.`class_id` = 1
  AND a.`spell_id` = 845;

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 6),
    `source_note` = 'phase8_warrior_cleave_action_integrity_2026_07_25',
    `scope_note` = 'Remove functionally ineffective Cleave; retain healthy specialization-specific primary and AoE cycles'
WHERE `class_id` = 1
  AND `spec_tag` IN ('arms_warrior', 'fury_warrior')
  AND `role` = 'dps';
