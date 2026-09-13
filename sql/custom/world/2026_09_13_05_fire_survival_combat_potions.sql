-- Fire: the pinned APL potion branch requires known, cooldown-ready Combustion.
-- Survival: implement only the independently valid E20 branch. The alternate
-- remaining-time <=25s branch is not represented; no remaining time is inferred.
-- Bucket 0 precedes current combat bucket 1; sort alone does not outrank Score.
-- Real inventory/item cooldown and shared raid potion reservation remain native.
-- Preserve existing potion rows, disabled profiles, and all profile metadata.
INSERT INTO `bot_rotation_action`
 (`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
  `damage_weight`, `survival_weight`, `priority_bucket`, `min_enemies`, `max_enemies`,
  `target_selector`, `movement_directive`, `auto_attack_mode`, `min_range`, `max_range`,
  `max_hostile_target_health_pct`, `enabled`)
SELECT p.`id`, 24, 79476, 'use_item',
 'volcanic_potion,combat_potion,combustion_ready,pinned_apl',
 1.10, 0.00, 0, 1, 0, 'self', 'hold', 'none', 0, 0, 0, 1
FROM `bot_rotation_profile` p
WHERE p.`class_id` = 8 AND p.`spec_tag` = 'fire' AND p.`role` = 'dps' AND p.`enabled` = 1
 AND NOT EXISTS (SELECT 1 FROM `bot_rotation_action` a
                 WHERE a.`profile_id` = p.`id` AND a.`spell_id` = 79476);

INSERT INTO `bot_rotation_action`
 (`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
  `damage_weight`, `survival_weight`, `priority_bucket`, `min_enemies`, `max_enemies`,
  `target_selector`, `movement_directive`, `auto_attack_mode`, `min_range`, `max_range`,
  `max_hostile_target_health_pct`, `enabled`)
SELECT p.`id`, 16, 79633, 'use_item',
 'tolvir_potion,combat_potion,execute_20,pinned_apl_partial',
 1.10, 0.00, 0, 1, 0, 'self', 'hold', 'none', 0, 0, 0.20, 1
FROM `bot_rotation_profile` p
WHERE p.`class_id` = 3 AND p.`spec_tag` = 'survival' AND p.`role` = 'dps' AND p.`enabled` = 1
 AND NOT EXISTS (SELECT 1 FROM `bot_rotation_action` a
                 WHERE a.`profile_id` = p.`id` AND a.`spell_id` = 79633);
