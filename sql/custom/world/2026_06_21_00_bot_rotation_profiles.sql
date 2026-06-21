CREATE TABLE IF NOT EXISTS `bot_rotation_profile` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `class_id` TINYINT UNSIGNED NOT NULL,
  `spec_tag` VARCHAR(64) NOT NULL,
  `role` VARCHAR(32) NOT NULL,
  `resource_type` VARCHAR(32) NOT NULL DEFAULT 'mana',
  `range_band` VARCHAR(32) NOT NULL DEFAULT 'mixed',
  `movement_directive` VARCHAR(32) NOT NULL DEFAULT '',
  `auto_attack_mode` VARCHAR(16) NOT NULL DEFAULT '',
  `min_range` FLOAT NOT NULL DEFAULT 0,
  `max_range` FLOAT NOT NULL DEFAULT 0,
  `enabled` TINYINT UNSIGNED NOT NULL DEFAULT 1,
  `version` INT UNSIGNED NOT NULL DEFAULT 1,
  `source_note` VARCHAR(255) NOT NULL DEFAULT '',
  `scope_note` VARCHAR(255) NOT NULL DEFAULT 'add rows for any class_id/spec_tag/role to expand coverage',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_bot_rotation_profile` (`class_id`, `spec_tag`, `role`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

CREATE TABLE IF NOT EXISTS `bot_rotation_action` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `profile_id` INT UNSIGNED NOT NULL,
  `sort_order` SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  `spell_id` INT UNSIGNED NOT NULL DEFAULT 0,
  `category` VARCHAR(32) NOT NULL,
  `mechanic_tags` VARCHAR(255) NOT NULL DEFAULT '',
  `damage_weight` FLOAT NOT NULL DEFAULT 0,
  `healing_weight` FLOAT NOT NULL DEFAULT 0,
  `threat_weight` FLOAT NOT NULL DEFAULT 0,
  `mitigation_weight` FLOAT NOT NULL DEFAULT 0,
  `survival_weight` FLOAT NOT NULL DEFAULT 0,
  `movement_weight` FLOAT NOT NULL DEFAULT 0,
  `progression_weight` FLOAT NOT NULL DEFAULT 0,
  `profession_weight` FLOAT NOT NULL DEFAULT 0,
  `priority_bucket` TINYINT UNSIGNED NOT NULL DEFAULT 5,
  `min_enemies` TINYINT UNSIGNED NOT NULL DEFAULT 1,
  `max_enemies` TINYINT UNSIGNED NOT NULL DEFAULT 0,
  `min_target_health_pct` FLOAT NOT NULL DEFAULT 0,
  `max_target_health_pct` FLOAT NOT NULL DEFAULT 1,
  `min_self_health_pct` FLOAT NOT NULL DEFAULT 0,
  `max_self_health_pct` FLOAT NOT NULL DEFAULT 1,
  `required_self_aura` INT UNSIGNED NOT NULL DEFAULT 0,
  `forbidden_self_aura` INT UNSIGNED NOT NULL DEFAULT 0,
  `required_target_aura` INT UNSIGNED NOT NULL DEFAULT 0,
  `forbidden_target_aura` INT UNSIGNED NOT NULL DEFAULT 0,
  `requires_interruptible_target` TINYINT UNSIGNED NOT NULL DEFAULT 0,
  `requires_target_not_victim` TINYINT UNSIGNED NOT NULL DEFAULT 0,
  `requires_target_victim` TINYINT UNSIGNED NOT NULL DEFAULT 0,
  `requires_melee_range` TINYINT UNSIGNED NOT NULL DEFAULT 0,
  `requires_ranged_range` TINYINT UNSIGNED NOT NULL DEFAULT 0,
  `target_selector` VARCHAR(32) NOT NULL DEFAULT 'enemy',
  `movement_directive` VARCHAR(32) NOT NULL DEFAULT '',
  `auto_attack_mode` VARCHAR(16) NOT NULL DEFAULT '',
  `min_range` FLOAT NOT NULL DEFAULT 0,
  `max_range` FLOAT NOT NULL DEFAULT 0,
  `requires_instant_cast` TINYINT UNSIGNED NOT NULL DEFAULT 0,
  `max_cast_time_ms` INT UNSIGNED NOT NULL DEFAULT 0,
  `maintain_aura_id` INT UNSIGNED NOT NULL DEFAULT 0,
  `refresh_aura_below_ms` INT UNSIGNED NOT NULL DEFAULT 0,
  `enabled` TINYINT UNSIGNED NOT NULL DEFAULT 1,
  PRIMARY KEY (`id`),
  KEY `idx_bot_rotation_action_profile` (`profile_id`, `enabled`, `priority_bucket`, `sort_order`),
  CONSTRAINT `fk_bot_rotation_action_profile` FOREIGN KEY (`profile_id`) REFERENCES `bot_rotation_profile` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

DELETE a FROM `bot_rotation_action` a JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
WHERE p.`source_note` = 'stonecore_5n_cata_guide_seed';
DELETE FROM `bot_rotation_profile` WHERE `source_note` = 'stonecore_5n_cata_guide_seed';

INSERT INTO `bot_rotation_profile` (`class_id`, `spec_tag`, `role`, `resource_type`, `range_band`, `movement_directive`, `auto_attack_mode`, `min_range`, `max_range`, `version`, `source_note`, `scope_note`) VALUES
(2, 'protection', 'tank', 'mana_holy_power', 'melee', 'melee', 'melee', 0, 5, 1, 'stonecore_5n_cata_guide_seed', 'initial focused coverage for stonecore_5n; insert more rows for other specs'),
(5, 'holy_priest', 'healer', 'mana', 'ranged', 'healer_support', 'none', 18, 40, 1, 'stonecore_5n_cata_guide_seed', 'initial focused coverage for stonecore_5n; insert more rows for other specs'),
(8, 'fire', 'dps', 'mana', 'ranged', 'ranged', 'none', 12, 35, 1, 'stonecore_5n_cata_guide_seed', 'initial focused coverage for stonecore_5n; insert more rows for other specs'),
(3, 'marksmanship', 'dps', 'focus', 'ranged', 'ranged', 'ranged', 12, 35, 1, 'stonecore_5n_cata_guide_seed', 'initial focused coverage for stonecore_5n; insert more rows for other specs'),
(7, 'enhancement', 'dps', 'mana_maelstrom', 'melee', 'melee', 'melee', 0, 5, 1, 'stonecore_5n_cata_guide_seed', 'initial focused coverage for stonecore_5n; insert more rows for other specs');

INSERT INTO `bot_rotation_action` (`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`, `survival_weight`, `priority_bucket`, `min_enemies`, `target_selector`, `movement_directive`, `auto_attack_mode`, `maintain_aura_id`, `refresh_aura_below_ms`) VALUES
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=2 AND `spec_tag`='protection' AND `role`='tank'), 1, 25780, 'buff', 'righteous_fury,self,threat,prepull_required', 1.00, 0, 1, 'self', 'melee', 'melee', 25780, 300000),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=2 AND `spec_tag`='protection' AND `role`='tank'), 2, 31801, 'buff', 'seal_of_truth,self,threat,prepull_required', 0.95, 0, 1, 'self', 'melee', 'melee', 31801, 300000),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=2 AND `spec_tag`='protection' AND `role`='tank'), 3, 465, 'buff', 'devotion_aura,self,prepull_required', 0.85, 0, 1, 'self', 'melee', 'melee', 465, 300000),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=2 AND `spec_tag`='protection' AND `role`='tank'), 4, 20217, 'buff', 'blessing_of_kings,party,prepull_required', 0.85, 0, 1, 'party', 'melee', 'melee', 20217, 300000),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=2 AND `spec_tag`='protection' AND `role`='tank'), 5, 54428, 'buff', 'divine_plea,self,prepull_holy_power', 0.70, 0, 1, 'self', 'melee', 'melee', 54428, 0);

INSERT INTO `bot_rotation_action` (`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`, `damage_weight`, `healing_weight`, `threat_weight`, `mitigation_weight`, `survival_weight`, `priority_bucket`, `min_enemies`, `max_enemies`, `max_target_health_pct`, `max_self_health_pct`, `required_self_aura`, `forbidden_target_aura`, `requires_interruptible_target`, `requires_target_not_victim`, `requires_melee_range`) VALUES
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=2 AND `spec_tag`='protection' AND `role`='tank'), 10, 62124, 'taunt', 'hand_of_reckoning,taunt', 0, 0, 1.00, 0, 0.30, 1, 1, 0, 1, 1, 0, 0, 0, 1, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=2 AND `spec_tag`='protection' AND `role`='tank'), 20, 96231, 'interrupt', 'rebuke,interrupt', 0.15, 0, 0, 0, 0.20, 1, 1, 0, 1, 1, 0, 0, 1, 0, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=2 AND `spec_tag`='protection' AND `role`='tank'), 30, 498, 'defensive', 'divine_protection,defensive', 0, 0, 0, 0.90, 0.90, 1, 1, 0, 1, 0.55, 0, 0, 0, 0, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=2 AND `spec_tag`='protection' AND `role`='tank'), 40, 53595, 'cleave', 'hammer_of_the_righteous,aoe,holy_power,threat', 0.84, 0, 1.05, 0, 0, 2, 2, 0, 1, 1, 0, 0, 0, 0, 1),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=2 AND `spec_tag`='protection' AND `role`='tank'), 50, 26573, 'aoe', 'consecration,aoe,threat', 0.76, 0, 1.05, 0, 0, 2, 2, 0, 1, 1, 0, 0, 0, 0, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=2 AND `spec_tag`='protection' AND `role`='tank'), 60, 31935, 'threat_build', 'avengers_shield,ranged,shield,threat', 0.88, 0, 1.00, 0, 0, 2, 1, 0, 1, 1, 0, 0, 0, 0, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=2 AND `spec_tag`='protection' AND `role`='tank'), 70, 53600, 'spender', 'shield_of_the_righteous,holy_power,threat', 0.86, 0, 1.00, 0, 0, 2, 1, 0, 1, 1, 0, 0, 0, 0, 1),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=2 AND `spec_tag`='protection' AND `role`='tank'), 80, 2812, 'aoe', 'holy_wrath,aoe,threat', 0.74, 0, 0.92, 0, 0, 3, 2, 0, 1, 1, 0, 0, 0, 0, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=2 AND `spec_tag`='protection' AND `role`='tank'), 90, 35395, 'builder', 'crusader_strike,holy_power,threat,single_target', 0.76, 0, 0.65, 0, 0, 3, 1, 1, 1, 1, 0, 0, 0, 0, 1),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=2 AND `spec_tag`='protection' AND `role`='tank'), 100, 20271, 'builder', 'judgement,threat', 0.68, 0, 0.55, 0, 0, 4, 1, 0, 1, 1, 0, 0, 0, 0, 0);

INSERT INTO `bot_rotation_action` (`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`, `damage_weight`, `healing_weight`, `survival_weight`, `priority_bucket`, `min_enemies`, `max_target_health_pct`, `forbidden_target_aura`, `target_selector`, `movement_directive`, `auto_attack_mode`, `max_range`, `maintain_aura_id`) VALUES
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=5 AND `spec_tag`='holy_priest' AND `role`='healer'), 10, 33076, 'heal_efficient', 'prayer_of_mending,tank,heal,maintenance', 0, 0.86, 0.70, 1, 1, 0.98, 0, 'tank', 'healer_support', 'none', 40, 33076),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=5 AND `spec_tag`='holy_priest' AND `role`='healer'), 20, 2061, 'heal_fast', 'flash_heal,triage,heal', 0, 1.00, 0.85, 1, 1, 0.55, 0, 'lowest_ally', 'healer_support', 'none', 40, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=5 AND `spec_tag`='holy_priest' AND `role`='healer'), 30, 34861, 'heal_aoe', 'circle_of_healing,aoe,heal', 0, 0.94, 0.75, 1, 3, 0.85, 0, 'lowest_ally', 'healer_support', 'none', 40, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=5 AND `spec_tag`='holy_priest' AND `role`='healer'), 40, 139, 'heal_efficient', 'renew,hot,heal,maintenance', 0, 0.78, 0.65, 2, 1, 0.92, 139, 'tank', 'healer_support', 'none', 40, 139),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=5 AND `spec_tag`='holy_priest' AND `role`='healer'), 50, 2060, 'heal_efficient', 'greater_heal,big,heal', 0, 0.90, 0.75, 2, 1, 0.72, 0, 'tank', 'healer_support', 'none', 40, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=5 AND `spec_tag`='holy_priest' AND `role`='healer'), 60, 596, 'heal_aoe', 'prayer_of_healing,aoe,heal', 0, 0.88, 0.70, 2, 3, 0.80, 0, 'lowest_ally', 'healer_support', 'none', 40, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=5 AND `spec_tag`='holy_priest' AND `role`='healer'), 70, 2050, 'heal_efficient', 'heal,efficient,heal', 0, 0.74, 0.60, 3, 1, 0.88, 0, 'lowest_ally', 'healer_support', 'none', 40, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=5 AND `spec_tag`='holy_priest' AND `role`='healer'), 80, 527, 'dispel_cleanse', 'dispel,cleanse', 0, 0.25, 0.70, 1, 1, 1.00, 0, 'lowest_ally', 'healer_support', 'none', 40, 0);

INSERT INTO `bot_rotation_action` (`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`, `damage_weight`, `survival_weight`, `priority_bucket`, `min_enemies`, `required_self_aura`, `forbidden_target_aura`, `requires_interruptible_target`, `target_selector`, `movement_directive`, `auto_attack_mode`, `min_range`, `max_range`, `requires_instant_cast`, `max_cast_time_ms`) VALUES
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=8 AND `spec_tag`='fire' AND `role`='dps'), 10, 2139, 'interrupt', 'counterspell,interrupt', 0.15, 0.20, 1, 1, 0, 0, 1, 'enemy', 'ranged', 'none', 0, 35, 1, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=8 AND `spec_tag`='fire' AND `role`='dps'), 20, 44457, 'dot', 'living_bomb,maintain_debuff', 0.98, 0, 1, 1, 0, 44457, 0, 'enemy', 'ranged', 'none', 12, 35, 0, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=8 AND `spec_tag`='fire' AND `role`='dps'), 30, 92315, 'spender', 'pyroblast,hot_streak_only,instant_proc', 1.00, 0, 1, 1, 48108, 0, 0, 'enemy', 'ranged', 'none', 12, 35, 1, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=8 AND `spec_tag`='fire' AND `role`='dps'), 40, 2120, 'aoe', 'flamestrike,aoe', 0.90, 0, 3, 4, 0, 0, 0, 'enemy', 'ranged', 'none', 12, 35, 0, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=8 AND `spec_tag`='fire' AND `role`='dps'), 50, 133, 'builder', 'fireball,filler', 0.78, 0, 4, 1, 0, 0, 0, 'enemy', 'ranged', 'none', 12, 35, 0, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=8 AND `spec_tag`='fire' AND `role`='dps'), 60, 2136, 'spender', 'fire_blast,instant', 0.70, 0, 5, 1, 0, 0, 0, 'enemy', 'ranged', 'none', 12, 35, 1, 0);

INSERT INTO `bot_rotation_action` (`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`, `damage_weight`, `priority_bucket`, `min_enemies`, `max_target_health_pct`, `forbidden_target_aura`, `target_selector`, `movement_directive`, `auto_attack_mode`, `min_range`, `max_range`, `requires_ranged_range`) VALUES
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=3 AND `spec_tag`='marksmanship' AND `role`='dps'), 1, 13165, 'buff', 'aspect_of_the_hawk,self,prepull_required', 0.20, 0, 1, 1, 0, 'self', 'ranged', 'ranged', 12, 35, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=3 AND `spec_tag`='marksmanship' AND `role`='dps'), 2, 883, 'buff', 'call_pet,self,prepull_required', 0.20, 0, 1, 1, 0, 'self', 'ranged', 'ranged', 12, 35, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=3 AND `spec_tag`='marksmanship' AND `role`='dps'), 3, 982, 'buff', 'revive_pet,self,prepull_required', 0.20, 0, 1, 1, 0, 'self', 'ranged', 'ranged', 12, 35, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=3 AND `spec_tag`='marksmanship' AND `role`='dps'), 4, 34477, 'buff', 'misdirection,tank,prepull_threat', 0.25, 0, 1, 1, 0, 'tank', 'ranged', 'ranged', 12, 35, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=3 AND `spec_tag`='marksmanship' AND `role`='dps'), 5, 1130, 'debuff', 'hunters_mark,target,prepull', 0.35, 0, 1, 1, 1130, 'enemy', 'ranged', 'ranged', 12, 35, 1),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=3 AND `spec_tag`='marksmanship' AND `role`='dps'), 10, 1978, 'dot', 'serpent_sting,dot', 0.88, 1, 1, 1, 1978, 'enemy', 'ranged', 'ranged', 12, 35, 1),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=3 AND `spec_tag`='marksmanship' AND `role`='dps'), 20, 53209, 'spender', 'chimera_shot,focus,sting_refresh', 1.00, 1, 1, 1, 0, 'enemy', 'ranged', 'ranged', 12, 35, 1),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=3 AND `spec_tag`='marksmanship' AND `role`='dps'), 30, 53351, 'execute', 'kill_shot,execute', 1.00, 1, 1, 0.20, 0, 'enemy', 'ranged', 'ranged', 12, 35, 1),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=3 AND `spec_tag`='marksmanship' AND `role`='dps'), 40, 19434, 'spender', 'aimed_shot,focus', 0.92, 2, 1, 1, 0, 'enemy', 'ranged', 'ranged', 12, 35, 1),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=3 AND `spec_tag`='marksmanship' AND `role`='dps'), 50, 2643, 'aoe', 'multi_shot,aoe', 0.90, 2, 3, 1, 0, 'enemy', 'ranged', 'ranged', 12, 35, 1),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=3 AND `spec_tag`='marksmanship' AND `role`='dps'), 60, 3044, 'spender', 'arcane_shot,focus_dump', 0.80, 4, 1, 1, 0, 'enemy', 'ranged', 'ranged', 12, 35, 1),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=3 AND `spec_tag`='marksmanship' AND `role`='dps'), 70, 56641, 'builder', 'steady_shot,focus_builder', 0.74, 5, 1, 1, 0, 'enemy', 'ranged', 'ranged', 12, 35, 1),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=3 AND `spec_tag`='marksmanship' AND `role`='dps'), 80, 75, 'auto_attack', 'auto_shot,ranged', 0.45, 7, 1, 1, 0, 'enemy', 'ranged', 'ranged', 12, 35, 1);

INSERT INTO `bot_rotation_action` (`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`, `damage_weight`, `priority_bucket`, `min_enemies`, `required_self_aura`, `forbidden_target_aura`, `requires_interruptible_target`, `requires_melee_range`) VALUES
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=7 AND `spec_tag`='enhancement' AND `role`='dps'), 10, 57994, 'interrupt', 'wind_shear,interrupt', 0.15, 1, 1, 0, 0, 1, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=7 AND `spec_tag`='enhancement' AND `role`='dps'), 20, 421, 'cleave', 'chain_lightning,maelstrom_5,aoe', 0.94, 1, 3, 53817, 0, 0, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=7 AND `spec_tag`='enhancement' AND `role`='dps'), 30, 403, 'builder', 'lightning_bolt,maelstrom_5', 0.88, 1, 1, 53817, 0, 0, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=7 AND `spec_tag`='enhancement' AND `role`='dps'), 40, 17364, 'builder', 'stormstrike,melee', 0.96, 1, 1, 0, 0, 0, 1),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=7 AND `spec_tag`='enhancement' AND `role`='dps'), 50, 60103, 'spender', 'lava_lash,melee', 0.92, 2, 1, 0, 0, 0, 1),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=7 AND `spec_tag`='enhancement' AND `role`='dps'), 60, 8050, 'dot', 'flame_shock,dot', 0.84, 2, 1, 0, 8050, 0, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=7 AND `spec_tag`='enhancement' AND `role`='dps'), 70, 8042, 'spender', 'earth_shock', 0.76, 4, 1, 0, 0, 0, 0);
