-- Restore only rows changed by the matching migration.
UPDATE `bot_rotation_action`
SET `min_range` = 12,
    `mechanic_tags` = REPLACE(`mechanic_tags`, ',native_min_range_20260912', '')
WHERE `profile_id` IN (
  SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 7 AND `spec_tag` = 'elemental_shaman'
    AND `role` = 'dps' AND `enabled` = 1
)
  AND `enabled` = 1
  AND `spell_id` IN (8050, 421, 403, 8042, 51505)
  AND `min_range` = 0
  AND `mechanic_tags` LIKE '%,native_min_range_20260912%';
