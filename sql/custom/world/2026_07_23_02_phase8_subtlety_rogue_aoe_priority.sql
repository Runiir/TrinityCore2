-- Phase 8 Subtlety Rogue AoE throughput correction.
-- Preserve the primary-target builder, maintenance, and finisher priority while
-- retaining Fan of Knives as the lower-priority multi-target energy fallback.

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`sort_order` = 80,
    a.`damage_weight` = 0.78,
    a.`priority_bucket` = 2,
    a.`min_primary_power_pct` = 0.35,
    a.`max_primary_power_pct` = 1.00,
    a.`mechanic_tags` = 'fan_of_knives,aoe,energy_spender,low_priority_fallback'
WHERE p.`class_id` = 4
  AND p.`spec_tag` = 'subtlety_rogue'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 51723;

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 19),
    `source_note` = 'phase8_subtlety_rogue_aoe_priority_2026_07_23',
    `scope_note` = 'Primary-target Subtlety priority with rogue poisons and low-priority Fan of Knives fallback'
WHERE `class_id` = 4
  AND `spec_tag` = 'subtlety_rogue'
  AND `role` = 'dps';
