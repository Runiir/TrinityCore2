-- Firestarter permits Scorch to use the native cast-while-moving path. Keep
-- the existing 40%-mana resource fallback intact and add a moving-only copy
-- for the high-mana windows where Fireball is movement-rejected.

DELETE FROM `bot_rotation_action`
WHERE `profile_id` IN (
    SELECT `id` FROM `bot_rotation_profile`
    WHERE `class_id` = 8 AND `spec_tag` = 'fire'
      AND `role` = 'dps' AND `enabled` = 1
)
  AND `spell_id` = 2948
  AND `mechanic_tags` = 'scorch,firestarter,moving_filler,movement_only';

INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
 `damage_weight`, `healing_weight`, `threat_weight`, `mitigation_weight`,
 `survival_weight`, `movement_weight`, `progression_weight`,
 `profession_weight`, `priority_bucket`, `min_enemies`, `max_enemies`,
 `min_target_health_pct`, `max_target_health_pct`, `min_self_health_pct`,
 `max_self_health_pct`, `required_self_aura`, `forbidden_self_aura`,
 `required_target_aura`, `forbidden_target_aura`,
 `requires_interruptible_target`, `requires_target_not_victim`,
 `requires_target_victim`, `requires_melee_range`, `requires_ranged_range`,
 `target_selector`, `movement_directive`, `auto_attack_mode`, `min_range`,
 `max_range`, `requires_instant_cast`, `max_cast_time_ms`, `maintain_aura_id`,
 `refresh_aura_below_ms`, `min_injured_players`, `max_injured_players`,
 `injured_health_pct`, `min_mana_pct`, `max_mana_pct`,
 `min_primary_power_pct`, `max_primary_power_pct`, `min_attackers`,
 `max_attackers`, `requires_stationary`, `requires_moving`,
 `required_self_aura_stacks`, `max_self_aura_stacks`,
 `min_self_aura_remaining_ms`, `max_self_aura_remaining_ms`,
 `required_owned_target_aura`, `forbidden_owned_target_aura`,
 `min_combo_points`, `max_combo_points`, `min_ready_runes`,
 `required_shapeshift_form`, `requires_pet`, `forbids_pet`,
 `required_main_hand_enchant`, `required_off_hand_enchant`, `cooldown_group`,
 `target_creature_type_mask`, `requires_ground_target`,
 `min_hostile_target_health_pct`, `required_self_aura_charges`,
 `max_self_aura_charges`, `min_owned_target_aura_remaining_ms`,
 `max_hostile_target_health_pct`, `enabled`)
SELECT DISTINCT
  `action`.`profile_id`, 56, `action`.`spell_id`, `action`.`category`,
  'scorch,firestarter,moving_filler,movement_only',
  `action`.`damage_weight`, `action`.`healing_weight`, `action`.`threat_weight`,
  `action`.`mitigation_weight`, `action`.`survival_weight`,
  `action`.`movement_weight`, `action`.`progression_weight`,
  `action`.`profession_weight`, `action`.`priority_bucket`,
  `action`.`min_enemies`, `action`.`max_enemies`,
  `action`.`min_target_health_pct`, `action`.`max_target_health_pct`,
  `action`.`min_self_health_pct`, `action`.`max_self_health_pct`,
  `action`.`required_self_aura`, `action`.`forbidden_self_aura`,
  `action`.`required_target_aura`, `action`.`forbidden_target_aura`,
  `action`.`requires_interruptible_target`,
  `action`.`requires_target_not_victim`, `action`.`requires_target_victim`,
  `action`.`requires_melee_range`, `action`.`requires_ranged_range`,
  `action`.`target_selector`, `action`.`movement_directive`,
  `action`.`auto_attack_mode`, `action`.`min_range`, `action`.`max_range`,
  `action`.`requires_instant_cast`, `action`.`max_cast_time_ms`,
  `action`.`maintain_aura_id`, `action`.`refresh_aura_below_ms`,
  `action`.`min_injured_players`, `action`.`max_injured_players`,
  `action`.`injured_health_pct`, `action`.`min_mana_pct`, 1.00,
  `action`.`min_primary_power_pct`, `action`.`max_primary_power_pct`,
  `action`.`min_attackers`, `action`.`max_attackers`,
  `action`.`requires_stationary`, 1, `action`.`required_self_aura_stacks`,
  `action`.`max_self_aura_stacks`, `action`.`min_self_aura_remaining_ms`,
  `action`.`max_self_aura_remaining_ms`,
  `action`.`required_owned_target_aura`,
  `action`.`forbidden_owned_target_aura`, `action`.`min_combo_points`,
  `action`.`max_combo_points`, `action`.`min_ready_runes`,
  `action`.`required_shapeshift_form`, `action`.`requires_pet`,
  `action`.`forbids_pet`, `action`.`required_main_hand_enchant`,
  `action`.`required_off_hand_enchant`, `action`.`cooldown_group`,
  `action`.`target_creature_type_mask`, `action`.`requires_ground_target`,
  `action`.`min_hostile_target_health_pct`,
  `action`.`required_self_aura_charges`, `action`.`max_self_aura_charges`,
  `action`.`min_owned_target_aura_remaining_ms`,
  `action`.`max_hostile_target_health_pct`, `action`.`enabled`
FROM `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
WHERE `profile`.`class_id` = 8
  AND `profile`.`spec_tag` = 'fire'
  AND `profile`.`role` = 'dps'
  AND `profile`.`enabled` = 1
  AND `action`.`spell_id` = 2948
  AND `action`.`sort_order` = 55
  AND `action`.`category` = 'resource_generator'
  AND `action`.`mechanic_tags` = 'scorch,firestarter,moving_filler,resource_fallback'
  AND `action`.`priority_bucket` = 5
  AND `action`.`max_mana_pct` = 0.40
  AND `action`.`requires_stationary` = 0
  AND `action`.`requires_moving` = 0
  AND `action`.`enabled` = 1;
