-- Restore the Balance mushroom rows changed by
-- 2026_09_18_01_magmaw_balance_lava_mushrooms.sql.

DELETE FROM `spell_script_names`
WHERE `spell_id` = 78777
  AND `ScriptName` = 'spell_dru_wild_mushroom_damage';

SET @balance_profile := (
    SELECT `id`
    FROM `bot_rotation_profile`
    WHERE `class_id` = 11
      AND `spec_tag` = 'balance_druid'
      AND `role` = 'dps'
    LIMIT 1
);

UPDATE `bot_rotation_action`
SET `mechanic_tags` = 'wild_mushroom,prepull,pinned_apl',
    `target_selector` = 'enemy',
    `requires_ground_target` = 0
WHERE `profile_id` = @balance_profile
  AND `spell_id` = 88747
  AND `enabled` = 1;

UPDATE `bot_rotation_action`
SET `mechanic_tags` = 'wild_mushroom_detonate,solar_eclipse,pinned_apl',
    `target_selector` = 'self',
    `requires_ground_target` = 0
WHERE `profile_id` = @balance_profile
  AND `spell_id` = 88751
  AND `enabled` = 1;
