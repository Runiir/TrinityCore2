-- Phase 8 Protection Warrior tank-threat margin correction.
-- Live r5 evidence showed Cleave consuming six decisions for twelve total damage,
-- while every non-performance tank gate passed. Replace that broken rage dump
-- with the provisioned Shockwave talent to preserve explicit SQL authority and
-- add deterministic pack damage without changing the qualification floor.

DELETE a FROM `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
WHERE p.`class_id` = 1
  AND p.`spec_tag` = 'protection_warrior'
  AND p.`role` = 'tank'
  AND a.`spell_id` IN (845, 46968);

INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
 `damage_weight`, `threat_weight`, `mitigation_weight`, `survival_weight`,
 `priority_bucket`, `min_enemies`, `target_selector`, `movement_directive`,
 `auto_attack_mode`, `requires_melee_range`, `min_primary_power_pct`,
 `max_self_health_pct`, `maintain_aura_id`, `refresh_aura_below_ms`)
VALUES
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 1 AND `spec_tag` = 'protection_warrior' AND `role` = 'tank'),
 48, 46968, 'threat_build', 'shockwave,aoe,threat,rotation_primary,pack_damage',
 1.50, 2.00, 0.10, 0.00, 1, 2, 'enemy', 'melee', 'melee', 1, 0.10, 1.00, 0, 0);

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 19),
    `source_note` = 'phase8_protection_warrior_threat_margin_2026_07_25',
    `scope_note` = 'Replace non-damaging Cleave with Shockwave for stable tank-threat reference margin'
WHERE `class_id` = 1
  AND `spec_tag` = 'protection_warrior'
  AND `role` = 'tank';
