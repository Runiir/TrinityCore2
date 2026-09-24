-- Blood Death Knight tank: while Magmaw's Mangle holds the tank, Heart Strike
-- may spend a spare Blood rune. The Magmaw cooldown plan now owns the hold.
--
-- Follows 2026_09_23_40_blood_mangle_death_strike_runes.sql. That file gave
-- Heart Strike 55050 forbidden_self_aura 78412, the Mangle seat aura, because
-- Heart Strike had spent the Death runes that Death Strike needed
-- (bundle1-b8a539b kills 1 and 2). This file does not change the Icy Touch
-- and Plague Strike rows from 2026_09_23_41: those spells cost the Frost and
-- Unholy runes that Death Strike uses.
--
-- Evidence, smoke kill 2c0ed2d8-k1, Magmaw 10N, actor 30002 (Mgwtankb).
-- Seized at 89.8 s; the kill ended at 100.8 s.
--   * Heart Strike was rejected with forbidden_self_aura_active 136 times from
--     89.9 s to 100.8 s. In those 11 s the tank cast one Death Strike
--     (95.4 s), two Rune Strikes (98.0 s and 99.7 s) and Rune Tap (91.8 s,
--     off the GCD). That is 3 of about 7 global cooldowns.
--   * Death Strike failed its ready-rune gate for the whole window except the
--     95.4 s cast.
--   * Heart Strike costs one Blood rune. Spell::TakeRunePower pays with a
--     ready rune of the exact type before it uses any Death rune. Death Strike
--     costs Frost and Unholy, so it can never use a Blood rune. A ready Blood
--     rune is therefore wasted during the seizure unless Rune Tap needs it.
--
-- Change. Heart Strike's forbidden_self_aura goes back to 0.
-- BotMagmawMangleCooldownPlan.h HoldSeizedHeartStrike now holds Heart Strike
-- for any tank that carries a Mangle aura, even without the Magmaw board. It
-- is held unless both of these are true:
--   * Death Strike fails its native preflight.
--   * A ready Blood rune is left over after keeping one for a castable Rune Tap.
-- Death runes stay reserved for Death Strike. No rune, aura, damage or
-- cooldown is manufactured.
--
-- The migration is idempotent. The row update only changes a Heart Strike row
-- that still has the 78412 seat-aura restriction. The version bump never
-- lowers the version. The reverse migration is a commented block at the end
-- of this file, not a separate file: the worldserver auto-updater applies
-- every file in sql/custom/world at startup, so a separate revert file would
-- undo this one immediately.

UPDATE `bot_rotation_action`
SET `forbidden_self_aura` = 0
WHERE `profile_id` IN (
    SELECT `id` FROM `bot_rotation_profile`
    WHERE `class_id` = 6
      AND `spec_tag` = 'blood_death_knight'
      AND `role` = 'tank'
  )
  AND `spell_id` = 55050
  AND `required_self_aura` = 0
  AND `forbidden_self_aura` = 78412;

UPDATE `bot_rotation_profile`
SET `version` = CASE WHEN `version` < 33 THEN 33 ELSE `version` END,
    `source_note` = 'phase9_blood_seized_heart_strike_2026_09_24',
    `scope_note` = 'Heart Strike while seized by Magmaw only on a spare Blood rune when Death Strike cannot be cast (Magmaw cooldown plan); Icy Touch and Plague Strike stay held on seat aura 78412'
WHERE `class_id` = 6
  AND `spec_tag` = 'blood_death_knight'
  AND `role` = 'tank';

-- BEGIN REVERSE MIGRATION
-- UPDATE `bot_rotation_action`
-- SET `forbidden_self_aura` = 78412
-- WHERE `profile_id` IN (
--     SELECT `id` FROM `bot_rotation_profile`
--     WHERE `class_id` = 6
--       AND `spec_tag` = 'blood_death_knight'
--       AND `role` = 'tank'
--   )
--   AND `spell_id` = 55050
--   AND `required_self_aura` = 0
--   AND `forbidden_self_aura` = 0;
-- END REVERSE MIGRATION
