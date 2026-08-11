-- Phase 8 Survival qualification retains the productive opener Rapid Fire
-- timing while corrected character provisioning supplies the exact pinned
-- WoWSims ferocity pet talent ranks.

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`max_target_health_pct` = 1.00,
    a.`mechanic_tags` = 'rapid_fire,opener,cooldown,heroism_burst'
WHERE p.`class_id` = 3
  AND p.`spec_tag` = 'survival'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 3045;

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 8),
    `source_note` = 'phase8_survival_pet_reference_alignment_2026_07_22',
    `scope_note` = 'Exact ferocity pet talents with productive opener Rapid Fire timing'
WHERE `class_id` = 3
  AND `spec_tag` = 'survival'
  AND `role` = 'dps';
