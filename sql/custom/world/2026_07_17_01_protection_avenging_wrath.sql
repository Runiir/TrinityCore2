-- Protection uses Avenging Wrath as its offensive throughput/threat cooldown
-- when survival does not require holding it.  It is legal in both the
-- single-target and multi-target branches and targets the paladin.

DELETE `action` FROM `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id`=`action`.`profile_id`
WHERE `profile`.`class_id`=2 AND `profile`.`spec_tag`='protection' AND `profile`.`role`='tank'
  AND `action`.`spell_id`=31884;

INSERT INTO `bot_rotation_action`
(`profile_id`,`sort_order`,`spell_id`,`category`,`mechanic_tags`,`damage_weight`,`threat_weight`,
 `priority_bucket`,`min_enemies`,`target_selector`,`movement_directive`,`auto_attack_mode`)
VALUES
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id`=2 AND `spec_tag`='protection' AND `role`='tank'),
 15,31884,'offensive_cooldown','avenging_wrath,damage,threat,cooldown',1.20,1.10,
 1,1,'self','melee','melee');

UPDATE `bot_rotation_profile`
SET `version`=8,
    `source_note`='protection_avenging_wrath_2026_07_17',
    `scope_note`='Guide-aligned Holy Power priority, AoE threat, fillers, and offensive cooldown'
WHERE `class_id`=2 AND `spec_tag`='protection' AND `role`='tank';
