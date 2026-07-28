-- Phase 8 Survival qualification preserves every Explosive Shot periodic tick
-- during Lock and Load instead of replacing the owned periodic aura early.

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`maintain_aura_id` = 53301,
    a.`refresh_aura_below_ms` = 0,
    a.`mechanic_tags` = 'explosive_shot,highest_single_target_priority,preserve_periodic_ticks'
WHERE p.`class_id` = 3
  AND p.`spec_tag` = 'survival'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 53301;

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 6),
    `source_note` = 'phase8_survival_qualification_tuning_2026_07_21',
    `scope_note` = 'Into the Wilderness, Noxious Stings, and Lock and Load periodic-tick correctness'
WHERE `class_id` = 3
  AND `spec_tag` = 'survival'
  AND `role` = 'dps';
