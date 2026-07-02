DELETE a FROM `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
WHERE p.`role` = 'tank'
  AND (
    (p.`class_id` = 1 AND p.`spec_tag` = 'protection_warrior')
    OR (p.`class_id` = 6 AND p.`spec_tag` = 'blood_death_knight')
  );

INSERT INTO `bot_rotation_action` (`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`, `damage_weight`, `threat_weight`, `mitigation_weight`, `survival_weight`, `priority_bucket`, `min_enemies`, `requires_interruptible_target`, `requires_melee_range`, `target_selector`, `movement_directive`, `auto_attack_mode`, `maintain_aura_id`) VALUES
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=1 AND `spec_tag`='protection_warrior' AND `role`='tank'), 10, 6673, 'buff', 'battle_shout,self,threat,prepull_required', 0.10, 0.20, 0, 0.50, 0, 1, 0, 0, 'self', 'melee', 'melee', 6673),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=1 AND `spec_tag`='protection_warrior' AND `role`='tank'), 20, 469, 'buff', 'commanding_shout,self,prepull_required', 0, 0.10, 0.20, 0.60, 0, 1, 0, 0, 'self', 'melee', 'melee', 469),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=1 AND `spec_tag`='protection_warrior' AND `role`='tank'), 30, 355, 'taunt', 'taunt,threat_snap,protect_party', 0, 4.00, 0, 0.30, 0, 1, 0, 0, 'enemy', 'melee', 'melee', 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=1 AND `spec_tag`='protection_warrior' AND `role`='tank'), 35, 2565, 'defensive', 'shield_block,self,mitigation', 0, 0.10, 0.85, 0.70, 1, 1, 0, 0, 'self', 'melee', 'melee', 2565),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=1 AND `spec_tag`='protection_warrior' AND `role`='tank'), 40, 6552, 'interrupt', 'pummel,interrupt', 0.15, 0, 0, 0.20, 1, 1, 1, 1, 'enemy', 'melee', 'melee', 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=1 AND `spec_tag`='protection_warrior' AND `role`='tank'), 60, 78, 'threat_build', 'heroic_strike,threat,single_target', 0.74, 0.80, 0, 0, 2, 1, 0, 1, 'enemy', 'melee', 'melee', 0);

INSERT INTO `bot_rotation_action` (`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`, `damage_weight`, `healing_weight`, `threat_weight`, `mitigation_weight`, `survival_weight`, `priority_bucket`, `min_enemies`, `max_self_health_pct`, `requires_interruptible_target`, `requires_melee_range`, `target_selector`, `movement_directive`, `auto_attack_mode`, `maintain_aura_id`) VALUES
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=6 AND `spec_tag`='blood_death_knight' AND `role`='tank'), 10, 57330, 'buff', 'horn_of_winter,self,prepull_required', 0.15, 0, 0.20, 0, 0.40, 0, 1, 1.00, 0, 0, 'self', 'melee', 'melee', 57330),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=6 AND `spec_tag`='blood_death_knight' AND `role`='tank'), 12, 48263, 'buff', 'blood_presence,self,tank_stance,mitigation', 0, 0, 0.30, 0.90, 0.90, 0, 1, 1.00, 0, 0, 'self', 'melee', 'melee', 48263),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=6 AND `spec_tag`='blood_death_knight' AND `role`='tank'), 20, 49222, 'defensive', 'bone_shield,self,mitigation', 0, 0, 0.20, 0.85, 0.85, 1, 1, 0.90, 0, 0, 'self', 'melee', 'melee', 49222),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=6 AND `spec_tag`='blood_death_knight' AND `role`='tank'), 25, 48792, 'defensive', 'icebound_fortitude,self,mitigation', 0, 0, 0.10, 1.00, 1.00, 1, 1, 0.65, 0, 0, 'self', 'melee', 'melee', 48792),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=6 AND `spec_tag`='blood_death_knight' AND `role`='tank'), 28, 55233, 'defensive', 'vampiric_blood,self,mitigation,heal_amp', 0, 0.30, 0.10, 0.85, 1.00, 1, 1, 0.70, 0, 0, 'self', 'melee', 'melee', 55233),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=6 AND `spec_tag`='blood_death_knight' AND `role`='tank'), 30, 47528, 'interrupt', 'mind_freeze,interrupt', 0.15, 0, 0, 0, 0.20, 1, 1, 1.00, 1, 1, 'enemy', 'melee', 'melee', 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=6 AND `spec_tag`='blood_death_knight' AND `role`='tank'), 35, 56222, 'taunt', 'dark_command,taunt,threat_snap,protect_party', 0, 0, 4.00, 0, 0.30, 0, 1, 1.00, 0, 0, 'enemy', 'melee', 'melee', 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=6 AND `spec_tag`='blood_death_knight' AND `role`='tank'), 40, 49998, 'mitigation', 'death_strike,self_heal,melee,threat', 0.76, 0.80, 0.75, 0.65, 0.85, 1, 1, 1.00, 0, 1, 'enemy', 'melee', 'melee', 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=6 AND `spec_tag`='blood_death_knight' AND `role`='tank'), 45, 45477, 'threat_build', 'icy_touch,ranged_threat', 0.55, 0, 1.20, 0, 0, 2, 1, 1.00, 0, 0, 'enemy', 'melee', 'melee', 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=6 AND `spec_tag`='blood_death_knight' AND `role`='tank'), 50, 45462, 'builder', 'plague_strike,melee', 0.70, 0, 0.60, 0, 0, 3, 1, 1.00, 0, 1, 'enemy', 'melee', 'melee', 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=6 AND `spec_tag`='blood_death_knight' AND `role`='tank'), 60, 47541, 'spender', 'death_coil,runic_power', 0.68, 0, 0.45, 0, 0, 4, 1, 1.00, 0, 0, 'enemy', 'melee', 'melee', 0);
