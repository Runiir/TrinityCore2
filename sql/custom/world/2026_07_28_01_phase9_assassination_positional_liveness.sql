-- Phase 9 Assassination Rogue positional route liveness.
--
-- The second strict Phase 9 Stonecore canary completed all 14 route nodes,
-- but Assassination Rogue failed 68 of 358 actionable casts (18.99%). Every
-- failure was Backstab (spell 53) returning SPELL_FAILED_NOT_BEHIND. The
-- explicit action schema has no behind-position prerequisite, so execute-range
-- Backstab was selected while the route or encounter geometry did not place the
-- rogue behind the target. Mutilate remained the successful non-positional
-- builder and stays authoritative through execute range.

SET @assassination_profile := (
    SELECT `id`
    FROM `bot_rotation_profile`
    WHERE `class_id` = 4
      AND `spec_tag` = 'assassination_rogue'
      AND `role` = 'dps'
    LIMIT 1
);

UPDATE `bot_rotation_action`
SET `enabled` = 0
WHERE `profile_id` = @assassination_profile
  AND `spell_id` = 53;

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 9),
    `source_note` = 'phase9_assassination_positional_liveness_2026_07_28',
    `scope_note` = 'Use Mutilate as the legal builder when route geometry cannot guarantee a behind position'
WHERE `id` = @assassination_profile;
