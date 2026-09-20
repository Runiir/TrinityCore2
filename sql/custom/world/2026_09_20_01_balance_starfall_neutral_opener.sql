-- Keep the Balance opener aligned with the pinned single-target APL.
--
-- The typed candidate builder owns this exact neutral-state predicate; this
-- migration only binds it to Balance Starfall and preserves later eligibility.

SET @balance_profile := (
    SELECT `id`
    FROM `bot_rotation_profile`
    WHERE `class_id` = 11
      AND `spec_tag` = 'balance_druid'
      AND `role` = 'dps'
    LIMIT 1
);

UPDATE `bot_rotation_action`
SET `mechanic_tags` = CONCAT_WS(',', NULLIF(`mechanic_tags`, ''), 'balance_starfall_neutral_gate')
WHERE `profile_id` = @balance_profile
  AND `spell_id` = 48505
  AND `enabled` = 1
  AND FIND_IN_SET('balance_starfall_neutral_gate', `mechanic_tags`) = 0;
