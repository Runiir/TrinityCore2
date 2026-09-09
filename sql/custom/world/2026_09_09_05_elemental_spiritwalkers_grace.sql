-- Admit Spiritwalker's Grace only as the native capability that unblocks an
-- otherwise legal moving Lava Burst. Native known-spell, cooldown, GCD, aura
-- affect-mask, resource, range, target, and cast submission remain authoritative.

DELETE FROM `bot_rotation_action`
WHERE `profile_id` IN (
  SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 7
    AND `spec_tag` = 'elemental_shaman'
    AND `role` = 'dps'
    AND `enabled` = 1
)
  AND `spell_id` = 79206;

INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
 `damage_weight`, `priority_bucket`, `min_enemies`, `target_selector`,
 `movement_directive`, `auto_attack_mode`, `requires_moving`)
SELECT `id`, 16, 79206, 'offensive_cooldown',
       'unblock_moving_lava_burst', 1.00, 1, 1, 'self', 'ranged', 'none', 1
FROM `bot_rotation_profile`
WHERE `class_id` = 7
  AND `spec_tag` = 'elemental_shaman'
  AND `role` = 'dps'
  AND `enabled` = 1;
