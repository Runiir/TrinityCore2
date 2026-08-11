-- Phase 8 Holy Paladin qualification keeps deterministic triage responsive
-- without allowing expensive emergency healing to exhaust the 300-second
-- controlled-damage window.

DELETE a FROM `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
WHERE p.`class_id` = 2
  AND p.`spec_tag` = 'holy_paladin'
  AND p.`role` = 'healer'
  AND a.`spell_id` = 20473;

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`min_mana_pct` = 0.25
WHERE p.`class_id` = 2
  AND p.`spec_tag` = 'holy_paladin'
  AND p.`role` = 'healer'
  AND a.`spell_id` = 19750;

INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
 `healing_weight`, `survival_weight`, `priority_bucket`, `min_enemies`,
 `target_selector`, `movement_directive`, `auto_attack_mode`,
 `min_mana_pct`, `max_mana_pct`, `max_target_health_pct`)
VALUES
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 2 AND `spec_tag` = 'holy_paladin' AND `role` = 'healer'),
 15, 20473, 'heal_fast', 'holy_shock,triage,instant,holy_power',
 1.00, 0.85, 0, 1, 'lowest_ally', 'healer_support', 'none',
 0.05, 1.00, 0.94);
