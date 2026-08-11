-- Phase 8 Warrior productive AoE Rage fallback.
-- Removing functionally ineffective Cleave restored action integrity, but the
-- focused tuning140 Arms AoE proof then failed only the unchanged 0.20 resource
-- capping gate while passing the hard-reference target at 0.987786. Allow the
-- already healthy Heroic Strike action to consume excess Rage between Thunder
-- Clap, Sweeping Strikes, and Bladestorm windows. This is a primary-target AoE
-- fallback, not a replacement for the specialization's multi-target actions.

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`max_enemies` = 0,
    a.`mechanic_tags` = 'heroic_strike,rage_dump,single_target,aoe_fallback'
WHERE p.`class_id` = 1
  AND p.`spec_tag` IN ('arms_warrior', 'fury_warrior')
  AND p.`role` = 'dps'
  AND a.`spell_id` = 78;

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 7),
    `source_note` = 'phase8_warrior_heroic_strike_aoe_fallback_2026_07_25',
    `scope_note` = 'Use productive Heroic Strike as excess-Rage fallback after removing broken Cleave; retain primary multi-target actions'
WHERE `class_id` = 1
  AND `spec_tag` IN ('arms_warrior', 'fury_warrior')
  AND `role` = 'dps';
