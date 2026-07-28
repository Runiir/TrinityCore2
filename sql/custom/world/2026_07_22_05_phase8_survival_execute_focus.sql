-- Phase 8 Survival qualification restores the pinned 69-focus sustained dump
-- threshold and adds the APL's lower-focus end-of-fight burn inside the live
-- calibration execute window. Explosive Shot and Kill Shot remain authoritative.

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
  AND a.`spell_id` = 3044
  AND a.`mechanic_tags` = 'arcane_shot,execute_focus_burn,at_or_above_40_focus';

INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
 `damage_weight`, `survival_weight`, `priority_bucket`, `min_enemies`, `max_enemies`,
 `max_target_health_pct`, `min_primary_power_pct`, `target_selector`,
 `movement_directive`, `auto_attack_mode`, `min_range`, `max_range`)
VALUES
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 3 AND `spec_tag` = 'survival' AND `role` = 'dps'),
 75, 3044, 'spender', 'arcane_shot,execute_focus_burn,at_or_above_40_focus',
 0.82, 0.00, 5, 1, 1, 0.20, 0.40, 'enemy', 'ranged', 'ranged', 5, 35);

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 11),
    `source_note` = 'phase8_survival_execute_focus_2026_07_22',
    `scope_note` = 'Pinned 69-focus sustained dump plus lower-focus execute burn after Explosive Shot and Kill Shot'
WHERE `class_id` = 3
  AND `spec_tag` = 'survival'
  AND `role` = 'dps';
