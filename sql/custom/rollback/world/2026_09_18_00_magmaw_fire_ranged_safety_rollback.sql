-- Restore only rows tagged by 2026_09_18_00_magmaw_fire_ranged_safety.sql.
UPDATE `bot_rotation_action`
SET `min_range` = 0,
    `mechanic_tags` = REPLACE(`mechanic_tags`, ',magmaw_ranged_safety_20260918', '')
WHERE `profile_id` IN (
    SELECT `id`
    FROM `bot_rotation_profile`
    WHERE `class_id` = 8
      AND `spec_tag` = 'fire'
      AND `role` = 'dps'
      AND `enabled` = 1
  )
  AND `enabled` = 1
  AND `min_range` IN (9, 12)
  AND `mechanic_tags` LIKE '%,magmaw_ranged_safety_20260918%';

UPDATE `bot_rotation_profile`
SET `min_range` = 0,
    `version` = 2
WHERE `class_id` = 8
  AND `spec_tag` = 'fire'
  AND `role` = 'dps'
  AND `enabled` = 1
  AND `min_range` IN (9, 12)
  AND `version` = 3;
