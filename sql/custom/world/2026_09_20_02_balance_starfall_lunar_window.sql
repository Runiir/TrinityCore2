-- Keep Balance Starfall aligned with the pinned single-target APL after the opener.
--
-- The typed candidate builder owns the signed Eclipse/lunar-window predicate;
-- this migration only binds it to Balance Starfall and preserves the existing
-- neutral-opener tag on the same profile row.

SET @balance_profile := (
    SELECT `id`
    FROM `bot_rotation_profile`
    WHERE `class_id` = 11
      AND `spec_tag` = 'balance_druid'
      AND `role` = 'dps'
    LIMIT 1
);

UPDATE `bot_rotation_action`
SET `mechanic_tags` = CONCAT_WS(',', NULLIF(`mechanic_tags`, ''), 'balance_starfall_lunar_window')
WHERE `profile_id` = @balance_profile
  AND `spell_id` = 48505
  AND `enabled` = 1
  AND FIND_IN_SET('balance_starfall_lunar_window', `mechanic_tags`) = 0;
