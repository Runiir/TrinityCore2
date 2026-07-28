-- Phase 8 Survival qualification aligns sustained single-target timing with the
-- pinned simulator fixture: Rapid Fire is held for execute and Arcane Shot uses
-- the fixture's 69-focus dump threshold.

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`max_target_health_pct` = 0.20,
    a.`mechanic_tags` = 'rapid_fire,execute,cooldown,avoid_heroism_overlap'
WHERE p.`class_id` = 3
  AND p.`spec_tag` = 'survival'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 3045;

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`min_primary_power_pct` = 0.69,
    a.`mechanic_tags` = 'arcane_shot,focus_dump,at_or_above_69_focus'
WHERE p.`class_id` = 3
  AND p.`spec_tag` = 'survival'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 3044;

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 7),
    `source_note` = 'phase8_survival_reference_timing_2026_07_22',
    `scope_note` = 'Rapid Fire execute timing and exact 69-focus Arcane Shot threshold'
WHERE `class_id` = 3
  AND `spec_tag` = 'survival'
  AND `role` = 'dps';
