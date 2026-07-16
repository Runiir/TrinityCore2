-- Dummy-calibration findings from run 189. These preserve the guide priority
-- while closing measured global-use gaps before the next Stonecore attempt.

-- Fire: Blast Wave supplies a real multi-target cooldown. Impact-empowered
-- Fire Blast spreads active fire DoTs instead of remaining movement-only.
DELETE `action` FROM `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id`=`action`.`profile_id`
WHERE `profile`.`class_id`=8 AND `profile`.`spec_tag`='fire' AND `profile`.`role`='dps'
  AND `action`.`spell_id`=11113;
INSERT INTO `bot_rotation_action`
(`profile_id`,`sort_order`,`spell_id`,`category`,`mechanic_tags`,`damage_weight`,`priority_bucket`,
 `min_enemies`,`target_selector`,`movement_directive`,`auto_attack_mode`,`max_range`)
VALUES
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=8 AND `spec_tag`='fire' AND `role`='dps'),
 15,11113,'aoe','blast_wave,aoe,on_cooldown',1.10,1,3,'enemy','ranged','none',35);

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id`=`action`.`profile_id`
SET `action`.`category`='aoe', `action`.`mechanic_tags`='fire_blast,impact,dot_spread,aoe',
    `action`.`damage_weight`=1.15, `action`.`priority_bucket`=1,
    `action`.`min_enemies`=2, `action`.`required_self_aura`=64343,
    `action`.`requires_moving`=0
WHERE `profile`.`class_id`=8 AND `profile`.`spec_tag`='fire' AND `profile`.`role`='dps'
  AND `action`.`spell_id`=2136;

-- Enhancement: Unleash Flame must precede Flame Shock so the DoT consumes
-- the intended buff instead of repeatedly wasting it while Flame Shock lives.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id`=`action`.`profile_id`
SET `action`.`priority_bucket`=1
WHERE `profile`.`class_id`=7 AND `profile`.`spec_tag`='enhancement' AND `profile`.`role`='dps'
  AND `action`.`spell_id`=73680;

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id`=`action`.`profile_id`
SET `action`.`priority_bucket`=1, `action`.`required_self_aura`=73683,
    `action`.`mechanic_tags`='flame_shock,dot,requires_unleash_flame'
WHERE `profile`.`class_id`=7 AND `profile`.`spec_tag`='enhancement' AND `profile`.`role`='dps'
  AND `action`.`spell_id`=8050;

UPDATE `bot_rotation_profile`
SET `version`=5, `source_note`='dummy_calibration_run_189_tuning_2026_07_16'
WHERE (`class_id`=2 AND `spec_tag`='protection' AND `role`='tank')
   OR (`class_id`=8 AND `spec_tag`='fire' AND `role`='dps')
   OR (`class_id`=7 AND `spec_tag`='enhancement' AND `role`='dps');
