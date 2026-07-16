-- The Cataclysm Enhancement opener uses Fire Elemental Totem before falling
-- back to Searing Totem.  It is a real long cooldown, not a calibration-only
-- coefficient, and the runtime totem controller preserves it until expiry.

DELETE `action` FROM `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id`=`action`.`profile_id`
WHERE `profile`.`class_id`=7 AND `profile`.`spec_tag`='enhancement' AND `profile`.`role`='dps'
  AND `action`.`spell_id`=2894;

INSERT INTO `bot_rotation_action`
(`profile_id`,`sort_order`,`spell_id`,`category`,`mechanic_tags`,`damage_weight`,
 `priority_bucket`,`min_enemies`,`target_selector`,`movement_directive`,`auto_attack_mode`)
VALUES
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id`=7 AND `spec_tag`='enhancement' AND `role`='dps'),
 5,2894,'offensive_cooldown','fire_elemental_totem,opener,long_cooldown',1.35,
 0,1,'self','melee','melee');

UPDATE `bot_rotation_profile`
SET `version`=7,
    `source_note`='guide_aligned_fire_elemental_opener_2026_07_16',
    `scope_note`='Enhancement priority with Fire Elemental opener and Searing fallback'
WHERE `class_id`=7 AND `spec_tag`='enhancement' AND `role`='dps';
