-- Phase 8 Restoration Druid controlled-healing overheal correction.
-- Preserve the proven healing profile while delaying Rejuvenation until the
-- selected target is at or below 90% health.

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`injured_health_pct` = 0.90,
    a.`max_target_health_pct` = 0.90
WHERE p.`class_id` = 11
  AND p.`spec_tag` = 'restoration_druid'
  AND p.`role` = 'healer'
  AND a.`spell_id` = 774;

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 18),
    `source_note` = 'phase8_restoration_druid_overheal_2026_07_23',
    `scope_note` = 'Controlled-healing profile with delayed Rejuvenation eligibility'
WHERE `class_id` = 11
  AND `spec_tag` = 'restoration_druid'
  AND `role` = 'healer';
