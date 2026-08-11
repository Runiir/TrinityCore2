-- Phase 8 Combat Rogue AoE qualification fix.
-- Keep the primary-target Combat rotation available against multi-target packs and
-- activate Blade Flurry as the explicit cleave group once at least two enemies exist.

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`max_enemies` = 0
WHERE p.`class_id` = 4
  AND p.`spec_tag` = 'combat_rogue'
  AND p.`role` = 'dps';

DELETE duplicate
FROM `bot_rotation_action` duplicate
JOIN `bot_rotation_action` canonical
  ON canonical.`profile_id` = duplicate.`profile_id`
 AND canonical.`spell_id` = duplicate.`spell_id`
 AND canonical.`id` < duplicate.`id`
JOIN `bot_rotation_profile` p ON p.`id` = duplicate.`profile_id`
WHERE p.`class_id` = 4
  AND p.`spec_tag` = 'combat_rogue'
  AND p.`role` = 'dps'
  AND duplicate.`spell_id` = 13877;

INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
 `damage_weight`, `survival_weight`, `priority_bucket`, `min_enemies`, `max_enemies`,
 `target_selector`, `movement_directive`, `auto_attack_mode`, `min_range`, `max_range`,
 `maintain_aura_id`, `refresh_aura_below_ms`)
SELECT p.`id`, 15, 13877, 'aoe', 'blade_flurry,aoe,cleave',
       0.95, 0.00, 1, 2, 0,
       'self', 'melee', 'melee', 0, 0,
       13877, 0
FROM `bot_rotation_profile` p
WHERE p.`class_id` = 4
  AND p.`spec_tag` = 'combat_rogue'
  AND p.`role` = 'dps'
  AND NOT EXISTS (
    SELECT 1
    FROM `bot_rotation_action` existing
    WHERE existing.`profile_id` = p.`id`
      AND existing.`spell_id` = 13877
  );

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`sort_order` = 15,
    a.`category` = 'aoe',
    a.`mechanic_tags` = 'blade_flurry,aoe,cleave',
    a.`damage_weight` = 0.95,
    a.`survival_weight` = 0.00,
    a.`priority_bucket` = 1,
    a.`min_enemies` = 2,
    a.`max_enemies` = 0,
    a.`target_selector` = 'self',
    a.`movement_directive` = 'melee',
    a.`auto_attack_mode` = 'melee',
    a.`min_range` = 0,
    a.`max_range` = 0,
    a.`maintain_aura_id` = 13877,
    a.`refresh_aura_below_ms` = 0,
    a.`enabled` = 1
WHERE p.`class_id` = 4
  AND p.`spec_tag` = 'combat_rogue'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 13877;

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 17),
    `source_note` = 'phase8_combat_rogue_aoe_2026_07_22',
    `scope_note` = 'Primary-target Combat rotation with explicit Blade Flurry cleave'
WHERE `class_id` = 4
  AND `spec_tag` = 'combat_rogue'
  AND `role` = 'dps';
