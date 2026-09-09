-- Improved Steady Shot's passive talent is53221; its triggered haste aura is
-- 53220 (spell_hun_improved_steady_shot after two56641 casts). Observe the
-- triggered aura for the existing absent/expiring Steady Shot rows.
UPDATE `bot_rotation_action`
SET `forbidden_self_aura` = 53220
WHERE `profile_id` IN (
    SELECT `id` FROM `bot_rotation_profile`
    WHERE `class_id` = 3 AND `spec_tag` = 'marksmanship' AND `role` = 'dps'
  )
  AND `spell_id` = 56641 AND `sort_order` = 70
  AND `forbidden_self_aura` = 53221;

UPDATE `bot_rotation_action`
SET `required_self_aura` = 53220
WHERE `profile_id` IN (
    SELECT `id` FROM `bot_rotation_profile`
    WHERE `class_id` = 3 AND `spec_tag` = 'marksmanship' AND `role` = 'dps'
  )
  AND `spell_id` = 56641 AND `sort_order` = 71
  AND `required_self_aura` = 53221;

-- The pinned APL also ends with an unconditional Steady Shot. Keep focus
-- generation available while the haste buff is healthy and spenders cannot
-- execute; equal weight/bucket leaves upkeep rows first by sort order.
INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
 `damage_weight`, `priority_bucket`, `min_enemies`, `target_selector`,
 `movement_directive`, `auto_attack_mode`, `min_range`, `max_range`,
 `requires_stationary`)
SELECT `id`, 72, 56641, 'resource_generator',
 'steady_shot,focus_builder,apl_final_filler',
 0.74, 5, 1, 'enemy', 'ranged', 'ranged', 5, 40, 1
FROM `bot_rotation_profile`
WHERE `class_id` = 3 AND `spec_tag` = 'marksmanship' AND `role` = 'dps'
  AND NOT EXISTS (
    SELECT 1 FROM `bot_rotation_action`
    WHERE `profile_id` = `bot_rotation_profile`.`id`
      AND `spell_id` = 56641 AND `sort_order` = 72
      AND `mechanic_tags` = 'steady_shot,focus_builder,apl_final_filler'
  );
