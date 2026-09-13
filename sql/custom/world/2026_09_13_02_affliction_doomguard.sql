-- Affliction18540 is an instant, zero-range native self summon. Guardian
-- reservation owns prepull/trash admission; native cooldowns remain binding.
-- Preserve profile notes and action identity on replay; no unrelated rows.
UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 6)
WHERE `class_id` = 9 AND `spec_tag` = 'affliction_warlock'
  AND `role` = 'dps' AND `enabled` = 1;

INSERT INTO `bot_rotation_action` (`profile_id`, `sort_order`, `spell_id`, `category`)
SELECT p.`id`, 5, 18540, 'offensive_cooldown'
FROM `bot_rotation_profile` p
WHERE p.`class_id` = 9 AND p.`spec_tag` = 'affliction_warlock'
  AND p.`role` = 'dps' AND p.`enabled` = 1
  AND NOT EXISTS (
    SELECT 1 FROM `bot_rotation_action` a
    WHERE a.`profile_id` = p.`id` AND a.`spell_id` = 18540
  );

UPDATE `bot_rotation_action`
SET `sort_order` = 5, `category` = 'offensive_cooldown',
    `mechanic_tags` = 'summon_doomguard,guardian,pinned_apl',
    `damage_weight` = 1.20, `survival_weight` = 0,
    `priority_bucket` = 0, `min_enemies` = 1, `max_enemies` = 0,
    `target_selector` = 'self', `movement_directive` = 'ranged',
    `auto_attack_mode` = 'none', `min_range` = 0, `max_range` = 0,
    `requires_ranged_range` = 0, `enabled` = 1
WHERE `spell_id` = 18540 AND `profile_id` IN (
    SELECT `id` FROM `bot_rotation_profile`
    WHERE `class_id` = 9 AND `spec_tag` = 'affliction_warlock'
      AND `role` = 'dps' AND `enabled` = 1
  );
