-- Phase 9 Shadow Priest two-target route liveness.
--
-- Rerun23 reached High Priestess Azil under the strict 14-node route but
-- Shadow Priest active-action coverage was 0.4593. Immutable trace evidence
-- showed repeated states where all six direct damage actions were rejected by
-- max_enemies=1 while Mind Sear was rejected because it required three enemies.
-- Close only that two-target gap; preserve the Phase 8 single-target/AoE split.

SET @shadow_profile := (
    SELECT `id`
    FROM `bot_rotation_profile`
    WHERE `class_id` = 5
      AND `spec_tag` = 'shadow_priest'
      AND `role` = 'dps'
    LIMIT 1
);

UPDATE `bot_rotation_action`
SET `min_enemies` = 2,
    `max_enemies` = 0
WHERE `profile_id` = @shadow_profile
  AND `spell_id` = 48045;

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 3),
    `source_note` = 'phase9_shadow_priest_two_target_liveness_2026_07_29',
    `scope_note` = 'Use Mind Sear from two enemies upward while preserving single-target direct actions at max_enemies=1'
WHERE `id` = @shadow_profile;
