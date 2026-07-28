-- Phase 8 Subtlety Rogue AoE positional correction.
-- Backstab cannot execute against the front-facing AoE calibration target. Keep it
-- single-target-only and use the baseline rogue Sinister Strike as the legal
-- primary-target builder before the low-priority Fan of Knives fallback.

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`max_enemies` = 1
WHERE p.`class_id` = 4
  AND p.`spec_tag` = 'subtlety_rogue'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 53;

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`priority_bucket` = 0
WHERE p.`class_id` = 4
  AND p.`spec_tag` = 'subtlety_rogue'
  AND p.`role` = 'dps'
  AND a.`spell_id` IN (16511, 5171, 1943, 2098, 51713);

DELETE duplicate
FROM `bot_rotation_action` duplicate
JOIN `bot_rotation_action` canonical
  ON canonical.`profile_id` = duplicate.`profile_id`
 AND canonical.`spell_id` = duplicate.`spell_id`
 AND canonical.`id` < duplicate.`id`
JOIN `bot_rotation_profile` p ON p.`id` = duplicate.`profile_id`
WHERE p.`class_id` = 4
  AND p.`spec_tag` = 'subtlety_rogue'
  AND p.`role` = 'dps'
  AND duplicate.`spell_id` = 1752;

INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
 `damage_weight`, `priority_bucket`, `min_enemies`, `max_enemies`,
 `target_selector`, `movement_directive`, `auto_attack_mode`, `min_range`, `max_range`)
SELECT p.`id`, 35, 1752, 'builder', 'sinister_strike,aoe_primary_builder,positional_safe',
       0.96, 1, 2, 0,
       'enemy', 'melee', 'melee', 0, 5
FROM `bot_rotation_profile` p
WHERE p.`class_id` = 4
  AND p.`spec_tag` = 'subtlety_rogue'
  AND p.`role` = 'dps'
  AND NOT EXISTS (
    SELECT 1
    FROM `bot_rotation_action` existing
    WHERE existing.`profile_id` = p.`id`
      AND existing.`spell_id` = 1752
  );

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`sort_order` = 35,
    a.`category` = 'builder',
    a.`mechanic_tags` = 'sinister_strike,aoe_primary_builder,positional_safe',
    a.`damage_weight` = 0.96,
    a.`priority_bucket` = 1,
    a.`min_enemies` = 2,
    a.`max_enemies` = 0,
    a.`target_selector` = 'enemy',
    a.`movement_directive` = 'melee',
    a.`auto_attack_mode` = 'melee',
    a.`min_range` = 0,
    a.`max_range` = 5,
    a.`enabled` = 1
WHERE p.`class_id` = 4
  AND p.`spec_tag` = 'subtlety_rogue'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 1752;

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 20),
    `source_note` = 'phase8_subtlety_rogue_aoe_builder_2026_07_23',
    `scope_note` = 'Subtlety maintenance and finishers with positional-safe AoE primary builder, rogue poisons, and Fan of Knives fallback'
WHERE `class_id` = 4
  AND `spec_tag` = 'subtlety_rogue'
  AND `role` = 'dps';
