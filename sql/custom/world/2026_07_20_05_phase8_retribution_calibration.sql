-- Phase 8 Retribution calibration aligns the SQL-authoritative profile with
-- Cataclysm Holy Power, seal, Inquisition, and offensive cooldown mechanics.

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`mechanic_tags` = 'templars_verdict,holy_power,holy_power_3',
    a.`priority_bucket` = 1,
    a.`damage_weight` = 1.05
WHERE p.`class_id` = 2
  AND p.`spec_tag` = 'retribution_paladin'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 85256;

DELETE a FROM `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
WHERE p.`class_id` = 2
  AND p.`spec_tag` = 'retribution_paladin'
  AND p.`role` = 'dps'
  AND a.`spell_id` IN (31801, 31884, 84963, 85696);

INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
 `damage_weight`, `survival_weight`, `priority_bucket`, `min_enemies`,
 `max_enemies`, `target_selector`, `movement_directive`, `auto_attack_mode`,
 `requires_melee_range`, `min_primary_power_pct`, `maintain_aura_id`,
 `refresh_aura_below_ms`)
VALUES
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 2 AND `spec_tag` = 'retribution_paladin' AND `role` = 'dps'),
 1, 31801, 'buff', 'seal_of_truth,self,buff',
 0.20, 0.10, 0, 1, 0, 'self', 'melee', 'melee', 0, 0.00, 31801, 3000),
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 2 AND `spec_tag` = 'retribution_paladin' AND `role` = 'dps'),
 2, 84963, 'offensive_cooldown', 'inquisition,self,buff,holy_power_3',
 1.08, 0.00, 0, 1, 0, 'self', 'melee', 'melee', 0, 0.00, 84963, 3000),
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 2 AND `spec_tag` = 'retribution_paladin' AND `role` = 'dps'),
 3, 31884, 'offensive_cooldown', 'avenging_wrath,self,offensive_cooldown',
 1.00, 0.05, 0, 1, 0, 'self', 'melee', 'melee', 0, 0.00, 31884, 0),
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 2 AND `spec_tag` = 'retribution_paladin' AND `role` = 'dps'),
 4, 85696, 'offensive_cooldown', 'zealotry,self,offensive_cooldown,holy_power',
 1.00, 0.00, 0, 1, 0, 'self', 'melee', 'melee', 0, 0.00, 85696, 0);
