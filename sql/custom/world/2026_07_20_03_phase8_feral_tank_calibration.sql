-- Phase 8 Feral tank qualification uses Bear Form (FORM_BEAR = 5) for
-- every form-gated action. The inherited profile incorrectly required Cat Form.

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`required_shapeshift_form` = 5
WHERE p.`class_id` = 11
  AND p.`spec_tag` = 'feral_druid_tank'
  AND p.`role` = 'tank'
  AND a.`required_shapeshift_form` = 1;

-- Lacerate must build to three stacks before the SQL-tagged Pulverize spender
-- becomes eligible. The runtime interprets these explicit mechanic tags.
UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`forbidden_owned_target_aura` = 0,
    a.`maintain_aura_id` = 0,
    a.`refresh_aura_below_ms` = 0
WHERE p.`class_id` = 11
  AND p.`spec_tag` = 'feral_druid_tank'
  AND p.`role` = 'tank'
  AND a.`spell_id` = 33745;

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`required_owned_target_aura` = 33745
WHERE p.`class_id` = 11
  AND p.`spec_tag` = 'feral_druid_tank'
  AND p.`role` = 'tank'
  AND a.`spell_id` = 80313;

DELETE a FROM `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
WHERE p.`class_id` = 11
  AND p.`spec_tag` = 'feral_druid_tank'
  AND p.`role` = 'tank'
  AND a.`spell_id` IN (6807, 50334, 80964);

INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
 `damage_weight`, `threat_weight`, `mitigation_weight`, `survival_weight`,
 `priority_bucket`, `min_enemies`, `max_enemies`, `target_selector`,
 `movement_directive`, `auto_attack_mode`, `requires_melee_range`,
 `min_primary_power_pct`, `max_self_health_pct`, `maintain_aura_id`,
 `refresh_aura_below_ms`, `required_shapeshift_form`)
VALUES
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 11 AND `spec_tag` = 'feral_druid_tank' AND `role` = 'tank'),
 55, 6807, 'spender', 'maul,rage_dump,single_target,threat',
 0.95, 1.10, 0.00, 0.00, 3, 1, 1, 'enemy', 'melee', 'melee', 1,
 0.30, 1.00, 0, 0, 5),
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 11 AND `spec_tag` = 'feral_druid_tank' AND `role` = 'tank'),
 15, 50334, 'offensive_cooldown', 'berserk,self,offensive_cooldown,mangle_window',
 0.70, 0.30, 0.10, 0.10, 0, 1, 0, 'self', 'melee', 'melee', 0,
 0.00, 1.00, 50334, 0, 5);

INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
 `threat_weight`, `survival_weight`, `priority_bucket`, `min_enemies`,
 `target_selector`, `movement_directive`, `auto_attack_mode`,
 `requires_melee_range`, `requires_interruptible_target`,
 `required_shapeshift_form`)
VALUES
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 11 AND `spec_tag` = 'feral_druid_tank' AND `role` = 'tank'),
 12, 80964, 'interrupt', 'skull_bash,bear,interrupt,lockout',
 0.25, 0.20, 0, 1, 'enemy', 'melee', 'melee', 1, 1, 5);
