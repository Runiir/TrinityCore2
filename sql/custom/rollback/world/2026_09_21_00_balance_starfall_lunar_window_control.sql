-- Diagnostic control variant for an isolated matched Balance calibration.
-- Remove only the post-opener lunar-window tag from Balance Starfall. Reapply
-- 2026_09_20_02_balance_starfall_lunar_window.sql before leaving the database.

SET @balance_profile := (
    SELECT `id`
    FROM `bot_rotation_profile`
    WHERE `class_id` = 11
      AND `spec_tag` = 'balance_druid'
      AND `role` = 'dps'
    LIMIT 1
);

UPDATE `bot_rotation_action`
SET `mechanic_tags` = TRIM(BOTH ',' FROM REPLACE(
    CONCAT(',', `mechanic_tags`, ','),
    ',balance_starfall_lunar_window,',
    ','
))
WHERE `profile_id` = @balance_profile
  AND `spell_id` = 48505
  AND `enabled` = 1
  AND FIND_IN_SET('balance_starfall_lunar_window', `mechanic_tags`) > 0;
