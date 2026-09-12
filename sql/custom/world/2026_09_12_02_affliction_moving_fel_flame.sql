-- Keep proc Fel Flame in its stationary APL position. A separate last-choice
-- damage action may fill movement when maintenance, resources and proc actions
-- have no legal cast. Native spellbook, GCD, mana, range and cast state still gate it.
INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
 `damage_weight`, `priority_bucket`, `min_enemies`, `max_enemies`,
 `target_selector`, `movement_directive`, `auto_attack_mode`,
 `min_range`, `max_range`, `requires_moving`)
SELECT `p`.`id`, 140, 77799, 'builder', 'fel_flame,moving_filler_20260912',
       0.10, 14, 1, 0, 'enemy', 'ranged', 'none', 0, 40, 1
FROM `bot_rotation_profile` AS `p`
WHERE `p`.`class_id` = 9 AND `p`.`spec_tag` = 'affliction_warlock'
  AND `p`.`role` = 'dps' AND `p`.`enabled` = 1
  AND NOT EXISTS (
    SELECT 1 FROM `bot_rotation_action` AS `a`
    WHERE `a`.`profile_id` = `p`.`id`
      AND `a`.`spell_id` = 77799
      AND `a`.`mechanic_tags` = 'fel_flame,moving_filler_20260912'
  );
