-- Phase 8 Survival qualification separates Rapid Fire from the explicit
-- 40-second reference Heroism window and promotes Black Arrow maintenance so
-- Lock and Load opportunities are not delayed behind lower-value fillers.

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`forbidden_self_aura` = 2825,
    a.`priority_bucket` = 2,
    a.`mechanic_tags` = 'rapid_fire,cooldown,after_heroism,avoid_haste_overlap'
WHERE p.`class_id` = 3
  AND p.`spec_tag` = 'survival'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 3045;

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`priority_bucket` = 2,
    a.`sort_order` = 35,
    a.`mechanic_tags` = 'black_arrow,single_target,lock_and_load,maintenance_priority'
WHERE p.`class_id` = 3
  AND p.`spec_tag` = 'survival'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 3674;

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 12),
    `source_note` = 'phase8_survival_cooldown_separation_2026_07_22',
    `scope_note` = 'Rapid Fire after Heroism and prompt Black Arrow maintenance for stable sustained output'
WHERE `class_id` = 3
  AND `spec_tag` = 'survival'
  AND `role` = 'dps';
