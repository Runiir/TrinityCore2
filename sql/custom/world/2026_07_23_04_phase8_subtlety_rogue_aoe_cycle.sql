-- Phase 8 Subtlety Rogue AoE builder/spender cycle correction.
-- Use repeated Hemorrhage as the positional-safe multi-target primary builder,
-- spend at efficient combo-point thresholds, and reserve Fan of Knives for the
-- final execute segment so both primary-target and AoE groups remain observable.

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`damage_weight` = 0.98,
    a.`priority_bucket` = 1,
    a.`min_enemies` = 2,
    a.`max_enemies` = 0,
    a.`maintain_aura_id` = 0,
    a.`mechanic_tags` = 'hemorrhage,bleed,aoe_primary_builder,positional_safe'
WHERE p.`class_id` = 4
  AND p.`spec_tag` = 'subtlety_rogue'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 16511;

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`min_combo_points` = CASE
      WHEN a.`spell_id` = 1943 THEN 5
      WHEN a.`spell_id` = 2098 THEN 4
      ELSE a.`min_combo_points`
    END,
    a.`priority_bucket` = 0
WHERE p.`class_id` = 4
  AND p.`spec_tag` = 'subtlety_rogue'
  AND p.`role` = 'dps'
  AND a.`spell_id` IN (5171, 1943, 2098, 51713);

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`sort_order` = 80,
    a.`damage_weight` = 0.92,
    a.`priority_bucket` = 0,
    a.`min_enemies` = 2,
    a.`max_enemies` = 0,
    a.`min_target_health_pct` = 0.00,
    a.`max_target_health_pct` = 0.20,
    a.`min_primary_power_pct` = 0.35,
    a.`max_primary_power_pct` = 1.00,
    a.`mechanic_tags` = 'fan_of_knives,aoe,energy_spender,execute_segment'
WHERE p.`class_id` = 4
  AND p.`spec_tag` = 'subtlety_rogue'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 51723;

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 21),
    `source_note` = 'phase8_subtlety_rogue_aoe_cycle_2026_07_23',
    `scope_note` = 'Positional-safe Hemorrhage builder and efficient finishers with execute-segment Fan of Knives and rogue poisons'
WHERE `class_id` = 4
  AND `spec_tag` = 'subtlety_rogue'
  AND `role` = 'dps';
