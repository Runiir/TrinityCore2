-- Phase 9 Blood Death Knight follower threat retention.
--
-- Self-centered Death and Decay improved ordinary melee-trash placement but
-- regressed Azil because the persistent field remained behind the moving follower
-- cluster. Restore enemy-centered placement. Rerun15 showed Blood Boil acquiring
-- complete local waves and then losing them under focused party damage before the
-- followers died, so apply the same 1.9 damage-threat multiplier already used by
-- Death and Decay's 52212 trigger.

SET @blood_profile := (
    SELECT `id`
    FROM `bot_rotation_profile`
    WHERE `class_id` = 6
      AND `spec_tag` = 'blood_death_knight'
      AND `role` = 'tank'
    LIMIT 1
);

UPDATE `bot_rotation_action`
SET `target_selector` = 'ground_enemy'
WHERE `profile_id` = @blood_profile
  AND `spell_id` = 43265;

INSERT INTO `spell_threat` (`entry`, `flatMod`, `pctMod`, `apPctMod`)
VALUES (48721, 0, 1.9, 0.0)
ON DUPLICATE KEY UPDATE
    `flatMod` = VALUES(`flatMod`),
    `pctMod` = VALUES(`pctMod`),
    `apPctMod` = VALUES(`apPctMod`);

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 22),
    `source_note` = 'phase9_blood_boil_threat_retention_2026_07_29',
    `scope_note` = 'Use enemy-centered Death and Decay followed by Blood Boil with the same 1.9 area-threat multiplier as the persistent ground trigger'
WHERE `id` = @blood_profile;
