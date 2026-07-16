-- Cataclysm 4.3.4-compatible Stonecore priorities derived from the requested
-- Wowhead Cataclysm rotation guides. Runtime hard masks keep these priority
-- lists legal while encounter logic handles movement, threat, and targets.

ALTER TABLE `bot_rotation_action`
  ADD COLUMN IF NOT EXISTS `min_primary_power_pct` FLOAT NOT NULL DEFAULT 0 AFTER `max_mana_pct`,
  ADD COLUMN IF NOT EXISTS `max_primary_power_pct` FLOAT NOT NULL DEFAULT 1 AFTER `min_primary_power_pct`;

INSERT INTO `bot_rotation_profile`
(`class_id`, `spec_tag`, `role`, `resource_type`, `range_band`, `movement_directive`,
 `auto_attack_mode`, `min_range`, `max_range`, `version`, `source_note`, `scope_note`)
VALUES
(3, 'survival', 'dps', 'focus', 'ranged', 'ranged', 'ranged', 5, 35, 4,
 'wowhead_cata_survival_hunter_2026_07_16',
 'Explosive Shot priority; Black Arrow single target; Multi-Shot AoE; Cobra focus cycle; Misdirection threat transfer')
ON DUPLICATE KEY UPDATE
 `version` = VALUES(`version`), `source_note` = VALUES(`source_note`),
 `scope_note` = VALUES(`scope_note`), `enabled` = 1;

DELETE `action` FROM `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id` = `action`.`profile_id`
WHERE `profile`.`class_id` = 3 AND `profile`.`spec_tag` = 'survival' AND `profile`.`role` = 'dps';

INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`, `damage_weight`,
 `survival_weight`, `priority_bucket`, `min_enemies`, `max_enemies`, `max_target_health_pct`,
 `required_self_aura`, `forbidden_target_aura`, `target_selector`, `movement_directive`,
 `auto_attack_mode`, `min_range`, `max_range`, `requires_instant_cast`, `maintain_aura_id`,
 `min_primary_power_pct`)
VALUES
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=3 AND `spec_tag`='survival' AND `role`='dps'), 1, 13165, 'buff', 'aspect_of_the_hawk,self,prepull_required', 0.20, 0.20, 0, 1, 0, 1, 0, 0, 'self', 'ranged', 'ranged', 0, 0, 1, 13165, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=3 AND `spec_tag`='survival' AND `role`='dps'), 2, 883, 'buff', 'call_pet,self,prepull_required', 0, 0.50, 0, 1, 0, 1, 0, 0, 'self', 'ranged', 'ranged', 0, 0, 1, 0, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=3 AND `spec_tag`='survival' AND `role`='dps'), 3, 982, 'buff', 'revive_pet,self,prepull_required', 0, 0.50, 0, 1, 0, 1, 0, 0, 'self', 'ranged', 'ranged', 0, 0, 0, 0, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=3 AND `spec_tag`='survival' AND `role`='dps'), 4, 34477, 'buff', 'misdirection,tank,threat_transfer', 0.25, 0.20, 0, 1, 0, 1, 0, 0, 'tank', 'ranged', 'ranged', 0, 35, 1, 0, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=3 AND `spec_tag`='survival' AND `role`='dps'), 10, 2643, 'aoe', 'multi_shot,aoe,misdirection_transfer', 1.10, 0, 1, 2, 0, 1, 0, 0, 'enemy', 'ranged', 'ranged', 5, 35, 1, 0, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=3 AND `spec_tag`='survival' AND `role`='dps'), 20, 53301, 'spender', 'explosive_shot,highest_single_target_priority', 1.20, 0, 1, 1, 2, 1, 0, 0, 'enemy', 'ranged', 'ranged', 5, 35, 1, 0, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=3 AND `spec_tag`='survival' AND `role`='dps'), 30, 1978, 'dot', 'serpent_sting,maintain_debuff', 0.96, 0, 2, 1, 0, 1, 0, 1978, 'enemy', 'ranged', 'ranged', 5, 35, 1, 0, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=3 AND `spec_tag`='survival' AND `role`='dps'), 40, 13813, 'aoe', 'explosive_trap,aoe,two_plus_targets', 0.98, 0, 2, 2, 0, 1, 0, 0, 'enemy', 'ranged', 'ranged', 5, 35, 1, 0, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=3 AND `spec_tag`='survival' AND `role`='dps'), 50, 53351, 'execute', 'kill_shot,execute,after_explosive_shot', 1.00, 0, 3, 1, 0, 0.20, 0, 0, 'enemy', 'ranged', 'ranged', 5, 35, 1, 0, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=3 AND `spec_tag`='survival' AND `role`='dps'), 60, 3674, 'dot', 'black_arrow,single_target,lock_and_load', 0.98, 0, 4, 1, 1, 1, 0, 3674, 'enemy', 'ranged', 'ranged', 5, 35, 1, 0, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=3 AND `spec_tag`='survival' AND `role`='dps'), 70, 3044, 'spender', 'arcane_shot,focus_dump,over_70_focus', 0.82, 0, 5, 1, 2, 1, 0, 0, 'enemy', 'ranged', 'ranged', 5, 35, 1, 0, 0.70),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=3 AND `spec_tag`='survival' AND `role`='dps'), 80, 77767, 'resource_generator', 'cobra_shot,focus_builder,serpent_refresh', 0.78, 0, 6, 1, 0, 1, 0, 0, 'enemy', 'ranged', 'ranged', 5, 35, 0, 0, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=3 AND `spec_tag`='survival' AND `role`='dps'), 90, 1130, 'debuff', 'hunters_mark,prepull,maintenance', 0.10, 0, 7, 1, 0, 1, 0, 1130, 'enemy', 'ranged', 'ranged', 5, 35, 1, 0, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=3 AND `spec_tag`='survival' AND `role`='dps'), 100, 3045, 'offensive_cooldown', 'rapid_fire,opener,cooldown', 0.75, 0, 2, 1, 0, 1, 0, 0, 'self', 'ranged', 'ranged', 0, 0, 1, 0, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=3 AND `spec_tag`='survival' AND `role`='dps'), 110, 75, 'auto_attack', 'auto_shot,ranged', 0.45, 0, 8, 1, 0, 1, 0, 0, 'enemy', 'ranged', 'ranged', 5, 35, 1, 0, 0);

-- Protection: Hammer of the Righteous is the multi-target builder, followed
-- by Avenger's Shield, Consecration, and Holy Wrath. Single-target spenders
-- are masked out of multi-target branches.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id` = `action`.`profile_id`
SET `action`.`category` = CASE WHEN `action`.`spell_id` = 31935 THEN 'cleave' ELSE `action`.`category` END,
    `action`.`priority_bucket` = CASE
      WHEN `action`.`spell_id` = 62124 THEN 0
      WHEN `action`.`spell_id` = 53595 THEN 1
      WHEN `action`.`spell_id` = 31935 THEN 2
      WHEN `action`.`spell_id` = 26573 THEN 3
      WHEN `action`.`spell_id` = 2812 THEN 4
      ELSE `action`.`priority_bucket` END,
    `action`.`min_enemies` = CASE WHEN `action`.`spell_id` IN (53595, 26573, 2812) THEN 2 ELSE `action`.`min_enemies` END,
    `action`.`max_enemies` = CASE WHEN `action`.`spell_id` IN (35395, 53600) THEN 1 ELSE `action`.`max_enemies` END
WHERE `profile`.`class_id`=2 AND `profile`.`spec_tag`='protection' AND `profile`.`role`='tank';

DELETE `action` FROM `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id`=`action`.`profile_id`
WHERE `profile`.`class_id`=2 AND `profile`.`spec_tag`='protection' AND `profile`.`role`='tank'
  AND `action`.`spell_id`=84963;
INSERT INTO `bot_rotation_action`
(`profile_id`,`sort_order`,`spell_id`,`category`,`mechanic_tags`,`damage_weight`,`threat_weight`,
 `priority_bucket`,`min_enemies`,`target_selector`,`movement_directive`,`auto_attack_mode`)
VALUES
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=2 AND `spec_tag`='protection' AND `role`='tank'),
 45,84963,'spender','inquisition,holy_power,multi_target',0.80,0.90,2,2,'self','melee','melee');

-- Fire: proc Pyroblast, maintain Living Bomb, use Combustion with Ignite,
-- then Flame Orb/Fireball; Scorch is the movement filler and Flamestrike the
-- sustained AoE action.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id`=`action`.`profile_id`
SET `action`.`priority_bucket` = CASE
      WHEN `action`.`spell_id`=92315 THEN 0
      WHEN `action`.`spell_id`=44457 THEN 1
      WHEN `action`.`spell_id`=2120 THEN 2
      WHEN `action`.`spell_id`=2948 THEN 3
      WHEN `action`.`spell_id`=133 THEN 4
      WHEN `action`.`spell_id`=2136 THEN 5
      ELSE `action`.`priority_bucket` END,
    `action`.`min_enemies` = CASE WHEN `action`.`spell_id`=2120 THEN 3 ELSE `action`.`min_enemies` END
WHERE `profile`.`class_id`=8 AND `profile`.`spec_tag`='fire' AND `profile`.`role`='dps';

DELETE `action` FROM `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id`=`action`.`profile_id`
WHERE `profile`.`class_id`=8 AND `profile`.`spec_tag`='fire' AND `profile`.`role`='dps'
  AND `action`.`spell_id` IN (11129,82731,55342);
INSERT INTO `bot_rotation_action`
(`profile_id`,`sort_order`,`spell_id`,`category`,`mechanic_tags`,`damage_weight`,`priority_bucket`,
 `min_enemies`,`required_target_aura`,`target_selector`,`movement_directive`,`auto_attack_mode`,`max_range`)
VALUES
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=8 AND `spec_tag`='fire' AND `role`='dps'),25,11129,'spender','combustion,ignite_dot_window',1.20,2,1,12654,'enemy','ranged','none',35),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=8 AND `spec_tag`='fire' AND `role`='dps'),35,82731,'offensive_cooldown','flame_orb,on_cooldown',0.98,3,1,0,'enemy','ranged','none',35),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=8 AND `spec_tag`='fire' AND `role`='dps'),5,55342,'offensive_cooldown','mirror_image,opener,threat_reduction',0.72,1,1,0,'self','ranged','none',0);

-- Enhancement: maintain Flame Shock, keep totems through the runtime totem
-- controller, spend five Maelstrom stacks, use Stormstrike/Lava Lash on CD,
-- Unleash Elements, then Earth Shock only while Flame Shock is present.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id`=`action`.`profile_id`
SET `action`.`priority_bucket` = CASE
      WHEN `action`.`spell_id` IN (403,421) THEN 1
      WHEN `action`.`spell_id`=8050 THEN 1
      WHEN `action`.`spell_id`=17364 THEN 2
      WHEN `action`.`spell_id`=60103 THEN 3
      WHEN `action`.`spell_id`=8042 THEN 5
      ELSE `action`.`priority_bucket` END,
    `action`.`required_target_aura` = CASE WHEN `action`.`spell_id`=8042 THEN 8050 ELSE `action`.`required_target_aura` END,
    `action`.`required_self_aura_stacks` = CASE
      WHEN `action`.`spell_id` IN (403,421) THEN 5
      ELSE `action`.`required_self_aura_stacks` END
WHERE `profile`.`class_id`=7 AND `profile`.`spec_tag`='enhancement' AND `profile`.`role`='dps';

DELETE `action` FROM `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id`=`action`.`profile_id`
WHERE `profile`.`class_id`=7 AND `profile`.`spec_tag`='enhancement' AND `profile`.`role`='dps'
  AND `action`.`spell_id` IN (73680,51533);
INSERT INTO `bot_rotation_action`
(`profile_id`,`sort_order`,`spell_id`,`category`,`mechanic_tags`,`damage_weight`,`priority_bucket`,
 `min_enemies`,`target_selector`,`movement_directive`,`auto_attack_mode`,`requires_melee_range`)
VALUES
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=7 AND `spec_tag`='enhancement' AND `role`='dps'),15,51533,'offensive_cooldown','feral_spirit,opener,cooldown',1.05,1,1,'enemy','melee','melee',0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=7 AND `spec_tag`='enhancement' AND `role`='dps'),65,73680,'spender','unleash_elements,on_cooldown',0.84,4,1,'enemy','melee','melee',0);

-- Holy Priest: proactive shield/PoM, Chakra, Holy Word: Serenity spot heal,
-- dynamic Flash/Binding/Heal/Greater Heal, AoE healing, and existing emergency
-- cooldowns. Healer selection remains health- and incoming-damage-driven.
DELETE `action` FROM `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id`=`action`.`profile_id`
WHERE `profile`.`class_id`=5 AND `profile`.`spec_tag`='holy_priest' AND `profile`.`role`='healer'
  AND `action`.`spell_id` IN (17,14751,88625,32546);
INSERT INTO `bot_rotation_action`
(`profile_id`,`sort_order`,`spell_id`,`category`,`mechanic_tags`,`healing_weight`,`survival_weight`,
 `priority_bucket`,`min_enemies`,`max_target_health_pct`,`forbidden_target_aura`,`target_selector`,
 `movement_directive`,`auto_attack_mode`,`max_range`,`maintain_aura_id`,`min_injured_players`,`injured_health_pct`)
VALUES
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=5 AND `spec_tag`='holy_priest' AND `role`='healer'),1,14751,'buff','chakra,self,healing_stance',0.20,0.40,0,1,1,0,'self','healer_support','none',0,14751,0,1),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=5 AND `spec_tag`='holy_priest' AND `role`='healer'),2,17,'external_defensive','power_word_shield,tank,proactive',0.82,0.85,0,1,1,6788,'tank','healer_support','none',40,0,1,1),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=5 AND `spec_tag`='holy_priest' AND `role`='healer'),15,88625,'heal_fast','holy_word_serenity,spot_heal',1.05,0.85,1,1,0.92,0,'lowest_ally','healer_support','none',40,0,1,0.92),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=5 AND `spec_tag`='holy_priest' AND `role`='healer'),25,32546,'heal_fast','binding_heal,self_and_ally_emergency',0.98,0.90,1,1,0.60,0,'lowest_ally','healer_support','none',40,0,1,0.60);

UPDATE `bot_rotation_profile`
SET `version`=4, `source_note`='requested_wowhead_cata_rotation_guides_2026_07_16',
    `scope_note`='Stonecore guide-aligned priority, AoE, cooldown, and reactive healing profiles'
WHERE (`class_id`=2 AND `spec_tag`='protection' AND `role`='tank')
   OR (`class_id`=5 AND `spec_tag`='holy_priest' AND `role`='healer')
   OR (`class_id`=8 AND `spec_tag`='fire' AND `role`='dps')
   OR (`class_id`=7 AND `spec_tag`='enhancement' AND `role`='dps');
