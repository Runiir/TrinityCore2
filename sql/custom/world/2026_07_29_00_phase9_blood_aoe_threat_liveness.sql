-- Phase 9 Blood Death Knight multi-target threat liveness.
--
-- The first final-identity serial canary cleared all 14 Stonecore route nodes,
-- but Blood Death Knight retained only 80.91% of identity-scoped hostiles. The
-- dominant loss was an Azil wave of 60 hostiles: 57 simultaneously switched to
-- the healer while the immediate-AoE branch selected Dark Command, Heart
-- Strike, and Icy Touch. Blood Boil was legal at min_enemies=2 but remained in
-- priority bucket 1, behind every bucket-0 single-target threat action, and was
-- never attempted. Promote the explicit AoE threat action into the authoritative
-- bucket while retaining its multi-target gate.

SET @blood_profile := (
    SELECT `id`
    FROM `bot_rotation_profile`
    WHERE `class_id` = 6
      AND `spec_tag` = 'blood_death_knight'
      AND `role` = 'tank'
    LIMIT 1
);

UPDATE `bot_rotation_action`
SET `priority_bucket` = 0,
    `sort_order` = 32,
    `threat_weight` = GREATEST(`threat_weight`, 2.50),
    `min_enemies` = GREATEST(`min_enemies`, 2),
    `max_enemies` = 0,
    `enabled` = 1
WHERE `profile_id` = @blood_profile
  AND `spell_id` = 48721;

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 18),
    `source_note` = 'phase9_blood_aoe_threat_liveness_2026_07_29',
    `scope_note` = 'Prioritize Blood Boil over single-target builders whenever at least two hostiles are present'
WHERE `id` = @blood_profile;
