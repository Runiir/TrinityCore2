-- Phase 8 Fire Mage qualification preserves the SQL profile as runtime
-- authority while making sustained 300-second density calibration follow the
-- same resource cycle as the pinned full-raid reference.

DELETE a FROM `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
WHERE p.`class_id` = 8
  AND p.`spec_tag` = 'fire'
  AND p.`role` = 'dps'
  AND a.`spell_id` IN (5405, 6117, 12051, 30482);

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET
  a.`min_mana_pct` = CASE a.`spell_id`
    WHEN 133 THEN 0.00   -- Fireball
    WHEN 11113 THEN 0.00 -- Blast Wave
    WHEN 2120 THEN 0.50  -- Flamestrike only while the sustained AoE cycle has mana headroom
    WHEN 2136 THEN 0.00  -- Fire Blast
    WHEN 44457 THEN 0.00 -- Living Bomb
    WHEN 82731 THEN 0.00 -- Flame Orb
    ELSE a.`min_mana_pct`
  END,
  a.`max_mana_pct` = CASE a.`spell_id`
    WHEN 2948 THEN 0.40  -- Scorch begins before the cycle reaches starvation
    ELSE a.`max_mana_pct`
  END,
  a.`mechanic_tags` = CASE a.`spell_id`
    WHEN 2948 THEN 'scorch,firestarter,moving_filler,resource_fallback'
    ELSE a.`mechanic_tags`
  END,
  a.`requires_moving` = CASE a.`spell_id`
    WHEN 2948 THEN 0
    ELSE a.`requires_moving`
  END,
  a.`category` = CASE a.`spell_id`
    WHEN 2948 THEN 'resource_generator'
    ELSE a.`category`
  END,
  a.`priority_bucket` = CASE a.`spell_id`
    WHEN 2948 THEN 5
    ELSE a.`priority_bucket`
  END,
  a.`required_self_aura` = CASE a.`spell_id`
    WHEN 2136 THEN 64343 -- Impact proc: Fire Blast spreads active fire DoTs
    ELSE a.`required_self_aura`
  END
WHERE p.`class_id` = 8
  AND p.`spec_tag` = 'fire'
  AND p.`role` = 'dps'
  AND a.`spell_id` IN (133, 11113, 2120, 2136, 2948, 44457, 82731);

INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
 `survival_weight`, `priority_bucket`, `min_enemies`, `target_selector`,
 `movement_directive`, `auto_attack_mode`, `min_mana_pct`, `max_mana_pct`,
 `forbidden_self_aura`, `requires_stationary`)
VALUES
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 8 AND `spec_tag` = 'fire' AND `role` = 'dps'),
 44, 5405, 'use_item', 'mana_gem,mana_recovery,consumable',
 0.40, 0, 1, 'self', 'ranged', 'none', 0.00, 0.40, 0, 0),
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 8 AND `spec_tag` = 'fire' AND `role` = 'dps'),
 45, 12051, 'resource_generator', 'evocation,mana_recovery,channel',
 0.40, 0, 1, 'self', 'ranged', 'none', 0.00, 0.40, 0, 1),
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 8 AND `spec_tag` = 'fire' AND `role` = 'dps'),
 46, 6117, 'resource_generator', 'mage_armor,mana_recovery,low_mana_armor',
 0.40, 0, 1, 'self', 'ranged', 'none', 0.00, 0.10, 6117, 0),
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 8 AND `spec_tag` = 'fire' AND `role` = 'dps'),
 47, 30482, 'offensive_cooldown', 'molten_armor,mana_recovery_exit',
 0.40, 0, 1, 'self', 'ranged', 'none', 0.20, 1.00, 30482, 0);
