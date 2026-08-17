-- Align the Fire Mage runtime profile with the pinned WoWSims APL.
--
-- Evidence identity:
--   request: a33d85ae38cca571a13a6f53065b137b915972c6f54e39fdbd021c60acf0fd33
--   result:  7a46a27109876072d848f9728fcbd990053a99c9b80f53536d19cbbd2800a6b5
-- The native APL orders Combustion (priority_list[1..2]), Hot Streak
-- Pyroblast ([3]), Flame Orb ([4]), Living Bomb ([5]), Fireball ([10]),
-- Scorch ([11]), then unconditional Fire Blast ([12]).

-- Combustion must win the same priority tier as proc Pyroblast and must use
-- this mage's Ignite.  The C++ resolver still applies the live Ignite amount,
-- Living Bomb, and Pyroblast-window checks before accepting Combustion.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`priority_bucket` = 1,
    `action`.`required_target_aura` = 0,
    `action`.`required_owned_target_aura` = 12654
WHERE `profile`.`class_id` = 8
  AND `profile`.`spec_tag` = 'fire'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 11129;

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`priority_bucket` = 1
WHERE `profile`.`class_id` = 8
  AND `profile`.`spec_tag` = 'fire'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 92315;

-- Flame Orb is the APL action immediately before Living Bomb.  Keep both in
-- the same runtime tier and use sort order to preserve that APL order while
-- retaining the existing damage weights.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`priority_bucket` = 1,
    `action`.`sort_order` = 18
WHERE `profile`.`class_id` = 8
  AND `profile`.`spec_tag` = 'fire'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 82731;

-- Living Bomb is a per-mage DoT.  Do not suppress one Fire Mage because a
-- different mage owns the same spell aura on the target.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`forbidden_target_aura` = 0,
    `action`.`forbidden_owned_target_aura` = 44457
WHERE `profile`.`class_id` = 8
  AND `profile`.`spec_tag` = 'fire'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 44457;

-- The APL stops spending mana at 10%, then falls through to Scorch.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`min_mana_pct` = 0.10
WHERE `profile`.`class_id` = 8
  AND `profile`.`spec_tag` = 'fire'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 133;

-- The exact APL keeps unconditional Fire Blast as its final fallback.  The
-- existing row is Impact/AoE-only; retain that mechanic and add a separate
-- single-target fallback so the spell is not silently absent at one target.
INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
 `damage_weight`, `priority_bucket`, `min_enemies`, `target_selector`,
 `movement_directive`, `auto_attack_mode`, `min_range`, `max_range`,
 `requires_instant_cast`, `min_mana_pct`, `max_mana_pct`)
SELECT `profile`.`id`, 61, 2136, 'spender',
       'fire_blast,single_target_fallback,instant',
       0.70, 6, 1, 'enemy', 'ranged', 'none', 0, 35, 1, 0.00, 1.00
FROM `bot_rotation_profile` AS `profile`
WHERE `profile`.`class_id` = 8
  AND `profile`.`spec_tag` = 'fire'
  AND `profile`.`role` = 'dps'
  AND NOT EXISTS (
      SELECT 1
      FROM `bot_rotation_action` AS `existing`
      WHERE `existing`.`profile_id` = `profile`.`id`
        AND `existing`.`spell_id` = 2136
        AND `existing`.`mechanic_tags` = 'fire_blast,single_target_fallback,instant'
  );
