-- Phase 8 Subtlety Rogue AoE qualification fix.
-- Keep the primary-target Subtlety rotation available against multi-target packs and
-- add Fan of Knives as the explicit energy-spending AoE action.

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`max_enemies` = 0
WHERE p.`class_id` = 4
  AND p.`spec_tag` = 'subtlety_rogue'
  AND p.`role` = 'dps';

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
  AND duplicate.`spell_id` = 51723;

INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
 `damage_weight`, `priority_bucket`, `min_enemies`, `max_enemies`,
 `min_primary_power_pct`, `max_primary_power_pct`, `target_selector`,
 `movement_directive`, `auto_attack_mode`, `min_range`, `max_range`)
SELECT p.`id`, 15, 51723, 'aoe', 'fan_of_knives,aoe,energy_spender',
       0.98, 1, 2, 0,
       0.35, 1.00, 'enemy',
       'melee', 'melee', 0, 10
FROM `bot_rotation_profile` p
WHERE p.`class_id` = 4
  AND p.`spec_tag` = 'subtlety_rogue'
  AND p.`role` = 'dps'
  AND NOT EXISTS (
    SELECT 1
    FROM `bot_rotation_action` existing
    WHERE existing.`profile_id` = p.`id`
      AND existing.`spell_id` = 51723
  );

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`sort_order` = 15,
    a.`category` = 'aoe',
    a.`mechanic_tags` = 'fan_of_knives,aoe,energy_spender',
    a.`damage_weight` = 0.98,
    a.`priority_bucket` = 1,
    a.`min_enemies` = 2,
    a.`max_enemies` = 0,
    a.`min_primary_power_pct` = 0.35,
    a.`max_primary_power_pct` = 1.00,
    a.`target_selector` = 'enemy',
    a.`movement_directive` = 'melee',
    a.`auto_attack_mode` = 'melee',
    a.`min_range` = 0,
    a.`max_range` = 10,
    a.`enabled` = 1
WHERE p.`class_id` = 4
  AND p.`spec_tag` = 'subtlety_rogue'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 51723;

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 18),
    `source_note` = 'phase8_subtlety_rogue_aoe_2026_07_23',
    `scope_note` = 'Primary-target Subtlety rotation with explicit Fan of Knives AoE spending'
WHERE `class_id` = 4
  AND `spec_tag` = 'subtlety_rogue'
  AND `role` = 'dps';
