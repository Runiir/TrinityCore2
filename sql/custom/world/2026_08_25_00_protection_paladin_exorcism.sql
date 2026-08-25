-- Keep existing worlds aligned with the canonical level-85 Protection
-- Paladin spellbook and provide one native single-target ranged threat action.
DELETE a FROM `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
WHERE p.`class_id` = 2 AND p.`spec_tag` = 'protection'
  AND p.`role` = 'tank' AND a.`spell_id` = 879;

INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
 `damage_weight`, `threat_weight`, `priority_bucket`, `min_enemies`,
 `max_enemies`, `target_selector`, `movement_directive`, `auto_attack_mode`,
 `max_range`, `requires_stationary`)
SELECT p.`id`, 55, 879, 'threat_build',
       'exorcism,ranged,single_target,threat',
       0.82, 0.90, 2, 1, 1, 'enemy', 'ranged', 'none', 35, 1
FROM `bot_rotation_profile` p
WHERE p.`class_id` = 2 AND p.`spec_tag` = 'protection'
  AND p.`role` = 'tank' AND p.`enabled` = 1;
