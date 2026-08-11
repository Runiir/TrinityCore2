-- Phase 8 Protection Warrior qualification keeps explicit SQL actions as the
-- runtime authority while restoring the Cataclysm shield-slam priority cycle.

DELETE a FROM `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
WHERE p.`class_id` = 1
  AND p.`spec_tag` = 'protection_warrior'
  AND p.`role` = 'tank'
  AND a.`spell_id` IN (772, 6343, 871, 12809, 12975, 20243, 23922, 46968);

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`priority_bucket` = 2,
    a.`min_primary_power_pct` = 0.25,
    a.`mechanic_tags` = 'heroic_strike,threat,rage_dump,single_target'
WHERE p.`class_id` = 1
  AND p.`spec_tag` = 'protection_warrior'
  AND p.`role` = 'tank'
  AND a.`spell_id` = 78;

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`category` = 'resource_generator',
    a.`mechanic_tags` = 'battle_shout,self,rage_generator,resource_recovery',
    a.`priority_bucket` = 0,
    a.`max_primary_power_pct` = 0.35,
    a.`maintain_aura_id` = 0
WHERE p.`class_id` = 1
  AND p.`spec_tag` = 'protection_warrior'
  AND p.`role` = 'tank'
  AND a.`spell_id` = 6673;

INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
 `damage_weight`, `threat_weight`, `mitigation_weight`, `survival_weight`,
 `priority_bucket`, `min_enemies`, `target_selector`, `movement_directive`,
 `auto_attack_mode`, `requires_melee_range`, `min_primary_power_pct`,
 `max_self_health_pct`, `maintain_aura_id`, `refresh_aura_below_ms`)
VALUES
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 1 AND `spec_tag` = 'protection_warrior' AND `role` = 'tank'),
 45, 23922, 'threat_build', 'shield_slam,shield,threat,rotation_primary',
 1.00, 1.25, 0.00, 0.00, 1, 1, 'enemy', 'melee', 'melee', 1, 0.15, 1.00, 0, 0),
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 1 AND `spec_tag` = 'protection_warrior' AND `role` = 'tank'),
 46, 772, 'threat_build', 'rend,bleed,threat,rotation_secondary',
 0.80, 0.80, 0.00, 0.00, 2, 1, 'enemy', 'melee', 'melee', 1, 0.10, 1.00, 94009, 3000),
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 1 AND `spec_tag` = 'protection_warrior' AND `role` = 'tank'),
 49, 6343, 'threat_build', 'thunder_clap,aoe,threat,rotation_secondary',
 0.78, 1.00, 0.00, 0.00, 2, 1, 'enemy', 'melee', 'melee', 1, 0.20, 1.00, 0, 0),
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 1 AND `spec_tag` = 'protection_warrior' AND `role` = 'tank'),
 55, 20243, 'threat_build', 'devastate,sunder_armor,threat,rotation_filler',
 0.82, 0.95, 0.00, 0.00, 3, 1, 'enemy', 'melee', 'melee', 1, 0.10, 1.00, 0, 0),
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 1 AND `spec_tag` = 'protection_warrior' AND `role` = 'tank'),
 25, 12975, 'defensive', 'last_stand,self,defensive,health_pool',
 0.00, 0.10, 0.30, 1.00, 0, 1, 'self', 'melee', 'melee', 0, 0.00, 0.65, 12975, 0),
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 1 AND `spec_tag` = 'protection_warrior' AND `role` = 'tank'),
 26, 871, 'defensive', 'shield_wall,self,defensive,mitigation',
 0.00, 0.10, 1.00, 1.00, 0, 1, 'self', 'melee', 'melee', 0, 0.00, 0.50, 871, 0);
