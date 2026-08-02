-- Phase 9 Blood Death Knight ordinary-pull threat margin.
--
-- Rerun20 completed the strict 14-node route with low healer exposure, but
-- identity-scoped all-hostile retention was 0.8928: eight owned samples below
-- the unchanged 0.90 floor. The tank selected and approached loose hostiles,
-- while the existing 1.9 Blood Boil multiplier varied around the hard gate
-- under concentrated party damage. Raise only Blood Boil's threat multiplier
-- by a bounded 10.5%; preserve damage, routing, and all other tank profiles.

SET @blood_profile := (
    SELECT `id`
    FROM `bot_rotation_profile`
    WHERE `class_id` = 6
      AND `spec_tag` = 'blood_death_knight'
      AND `role` = 'tank'
    LIMIT 1
);

INSERT INTO `spell_threat` (`entry`, `flatMod`, `pctMod`, `apPctMod`)
VALUES (48721, 0, 2.1, 0.0)
ON DUPLICATE KEY UPDATE
    `flatMod` = VALUES(`flatMod`),
    `pctMod` = VALUES(`pctMod`),
    `apPctMod` = VALUES(`apPctMod`);

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 23),
    `source_note` = 'phase9_blood_boil_threat_margin_2026_07_29',
    `scope_note` = 'Use enemy-centered Death and Decay and a 2.1 Blood Boil area-threat multiplier for stable all-hostile ownership above the 0.90 floor'
WHERE `id` = @blood_profile;
