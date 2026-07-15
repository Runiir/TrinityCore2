-- Complete the Stonecore validation roster's core Cataclysm rotations.
-- Provisioning now supplies the matching legal spec talents and learned spells.

UPDATE `bot_rotation_profile`
SET `version` = 3,
    `scope_note` = 'DBC-validated spec build with sustained single-target, movement, cooldown, and AoE priorities'
WHERE (`class_id` = 2 AND `spec_tag` = 'protection' AND `role` = 'tank')
   OR (`class_id` = 8 AND `spec_tag` = 'fire' AND `role` = 'dps')
   OR (`class_id` = 3 AND `spec_tag` = 'marksmanship' AND `role` = 'dps')
   OR (`class_id` = 7 AND `spec_tag` = 'enhancement' AND `role` = 'dps');

-- Hot Streak and Combustion must outrank the filler once their aura/DoT gates
-- are satisfied. Fire Blast and Firestarter Scorch provide legal movement DPS.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id` = `action`.`profile_id`
SET `action`.`priority_bucket` = CASE
        WHEN `action`.`spell_id` IN (92315, 11129) THEN 1
        WHEN `action`.`spell_id` = 2136 THEN 3
        ELSE `action`.`priority_bucket`
    END,
    `action`.`requires_moving` = CASE WHEN `action`.`spell_id` = 2136 THEN 1 ELSE `action`.`requires_moving` END
WHERE `profile`.`class_id` = 8 AND `profile`.`spec_tag` = 'fire' AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` IN (92315, 11129, 2136);

DELETE `action` FROM `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id` = `action`.`profile_id`
WHERE `profile`.`class_id` = 8 AND `profile`.`spec_tag` = 'fire' AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 2948;

INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`, `damage_weight`, `priority_bucket`,
 `min_enemies`, `target_selector`, `movement_directive`, `auto_attack_mode`, `max_range`, `requires_moving`)
VALUES
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=8 AND `spec_tag`='fire' AND `role`='dps'),
 55, 2948, 'builder', 'scorch,firestarter,moving_filler', 0.74, 3, 1, 'enemy', 'ranged', 'none', 35, 1);

-- A five-stack Maelstrom cast is the Enhancement payoff and must win over a
-- newly available melee generator. The existing stack gates remain intact.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id` = `action`.`profile_id`
SET `action`.`damage_weight` = CASE WHEN `action`.`spell_id` = 421 THEN 1.25 ELSE 1.20 END,
    `action`.`priority_bucket` = 1
WHERE `profile`.`class_id` = 7 AND `profile`.`spec_tag` = 'enhancement' AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` IN (403, 421);

-- Keep the tank centered on multi-target work: taunt loose enemies first,
-- then establish area threat before returning to single-target spenders.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id` = `action`.`profile_id`
SET `action`.`priority_bucket` = CASE
        WHEN `action`.`spell_id` = 62124 THEN 0
        WHEN `action`.`spell_id` IN (53595, 26573) THEN 1
        WHEN `action`.`spell_id` = 2812 THEN 2
        ELSE `action`.`priority_bucket`
    END
WHERE `profile`.`class_id` = 2 AND `profile`.`spec_tag` = 'protection' AND `profile`.`role` = 'tank'
  AND `action`.`spell_id` IN (62124, 53595, 26573, 2812);
