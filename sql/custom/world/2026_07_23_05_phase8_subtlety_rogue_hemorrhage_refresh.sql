-- Phase 8 Subtlety Rogue AoE Hemorrhage refresh correction.
-- The multi-target profile intentionally uses Hemorrhage as its repeatable,
-- positional-safe primary builder, so do not suppress it while its bleed aura is active.

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`forbidden_owned_target_aura` = 0,
    a.`maintain_aura_id` = 0,
    a.`damage_weight` = 0.98,
    a.`priority_bucket` = 1,
    a.`min_enemies` = 2,
    a.`max_enemies` = 0,
    a.`mechanic_tags` = 'hemorrhage,bleed,aoe_primary_builder,positional_safe,repeatable'
WHERE p.`class_id` = 4
  AND p.`spec_tag` = 'subtlety_rogue'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 16511;

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 22),
    `source_note` = 'phase8_subtlety_rogue_hemorrhage_refresh_2026_07_23',
    `scope_note` = 'Repeatable positional-safe Hemorrhage builder and efficient finishers with execute-segment Fan of Knives and rogue poisons'
WHERE `class_id` = 4
  AND `spec_tag` = 'subtlety_rogue'
  AND `role` = 'dps';
