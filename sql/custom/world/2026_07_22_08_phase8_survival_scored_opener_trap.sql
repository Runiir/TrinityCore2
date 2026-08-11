-- Phase 8 Survival qualification restores the pinned 69-focus sustained dump
-- threshold and recreates the pinned pre-pull Explosive Trap opportunity after
-- the calibration reset intentionally removes warmup dynamic objects. Requiring
-- at least 30 seconds of the 40-second reference Heroism aura makes this a
-- scored-window opener only; it cannot repeat when the shared trap/Black Arrow
-- cooldown recovers.

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`min_primary_power_pct` = 0.69,
    a.`mechanic_tags` = 'arcane_shot,focus_dump,at_or_above_69_focus'
WHERE p.`class_id` = 3
  AND p.`spec_tag` = 'survival'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 3044
  AND a.`sort_order` = 70;

DELETE a FROM `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
WHERE p.`class_id` = 3
  AND p.`spec_tag` = 'survival'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 13813
  AND a.`mechanic_tags` = 'explosive_trap,single_target,scored_opener,lock_and_load';

INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
 `damage_weight`, `survival_weight`, `priority_bucket`, `min_enemies`, `max_enemies`,
 `required_self_aura`, `min_self_aura_remaining_ms`, `target_selector`,
 `movement_directive`, `auto_attack_mode`, `min_range`, `max_range`)
VALUES
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 3 AND `spec_tag` = 'survival' AND `role` = 'dps'),
 17, 13813, 'aoe', 'explosive_trap,single_target,scored_opener,lock_and_load',
 1.00, 0.00, 1, 1, 1, 2825, 30000, 'enemy', 'ranged', 'ranged', 0, 35);

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 14),
    `source_note` = 'phase8_survival_scored_opener_trap_2026_07_22',
    `scope_note` = 'Pinned 69-focus dump plus one scored-window opener Explosive Trap before Black Arrow'
WHERE `class_id` = 3
  AND `spec_tag` = 'survival'
  AND `role` = 'dps';
