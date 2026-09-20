-- Keep the Balance opener aligned with the pinned single-target APL.
--
-- Starsurge is a legal native spell at a fresh neutral target, but the APL
-- deliberately waits for Moonfire in NeutralPhase with zero Eclipse power.
-- The typed candidate builder owns this tagged state predicate; this
-- migration only binds it to Balance Starsurge.

SET @balance_profile := (
    SELECT `id`
    FROM `bot_rotation_profile`
    WHERE `class_id` = 11
      AND `spec_tag` = 'balance_druid'
      AND `role` = 'dps'
    LIMIT 1
);

UPDATE `bot_rotation_action`
SET `mechanic_tags` = CONCAT_WS(',', NULLIF(`mechanic_tags`, ''), 'balance_starsurge_neutral_gate')
WHERE `profile_id` = @balance_profile
  AND `spell_id` = 78674
  AND `enabled` = 1
  AND FIND_IN_SET('balance_starsurge_neutral_gate', `mechanic_tags`) = 0;
