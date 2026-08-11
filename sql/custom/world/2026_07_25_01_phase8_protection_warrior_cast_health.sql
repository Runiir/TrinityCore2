-- Phase 8 Protection Warrior cast-health correction.
-- Focused tuning138 evidence showed Shockwave selected 771 times, with every cast
-- failing SPELL_FAILED_OUT_OF_RANGE and starving Devastate and Shield Slam.
-- Remove both failed pack-damage experiments and retain the working Heroic Strike
-- rage dump; this restores the healthy r5 action cycle without weakening gates.

DELETE a FROM `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
WHERE p.`class_id` = 1
  AND p.`spec_tag` = 'protection_warrior'
  AND p.`role` = 'tank'
  AND a.`spell_id` IN (845, 46968);

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 20),
    `source_note` = 'phase8_protection_warrior_cast_health_2026_07_25',
    `scope_note` = 'Remove out-of-range Shockwave and broken Cleave; use Heroic Strike rage dump with the healthy primary cycle'
WHERE `class_id` = 1
  AND `spec_tag` = 'protection_warrior'
  AND `role` = 'tank';
