-- Phase 8 Protection Warrior deterministic snap-threat opener correction.
-- Thunder Clap must become the first legal pack-damage action once Battle Shout
-- has supplied its existing rage requirement. Keep the rage gate so an
-- unavailable Thunder Clap cannot starve resource recovery, but place the
-- action above the always-eligible single-target Taunt within bucket zero.

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`damage_weight` = 1.50,
    a.`threat_weight` = 4.00,
    a.`priority_bucket` = 0,
    a.`min_enemies` = 1,
    a.`min_primary_power_pct` = 0.20,
    a.`mechanic_tags` = 'thunder_clap,aoe,threat,rotation_primary,snap_threat,opener'
WHERE p.`class_id` = 1
  AND p.`spec_tag` = 'protection_warrior'
  AND p.`role` = 'tank'
  AND a.`spell_id` = 6343;

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 18),
    `source_note` = 'phase8_protection_warrior_snap_threat_2026_07_23',
    `scope_note` = 'Deterministic Thunder Clap pack-threat opener before the ten-second snap-threat sample'
WHERE `class_id` = 1
  AND `spec_tag` = 'protection_warrior'
  AND `role` = 'tank';
