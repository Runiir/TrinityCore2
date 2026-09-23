-- Blood Death Knight tank: no Icy Touch or Plague Strike while Magmaw's
-- Mangle holds the tank, so Death Strike gets the Frost and Unholy runes.
--
-- Follows 2026_09_23_40_blood_mangle_death_strike_runes.sql, which holds
-- Heart Strike on the same aura.
--
-- Evidence, fid16-8586fdd kills 1-5, Magmaw 10N, actor 30002 (Mgwtankb),
-- DamageModifier 16 with the Heart Strike hold applied:
--   * No Heart Strike was cast during any Mangle hold, so that hold works.
--   * Icy Touch and Plague Strike took the runes instead. Kill 1: Icy Touch
--     at 96.0 s and Plague Strike at 102.7 s, and no Death Strike in a 16 s
--     hold. Kill 3: Plague Strike at 94.7 s and Icy Touch at 101.1 s, one
--     Death Strike. Kills 2 and 4: one Icy Touch each, two Death Strikes.
--   * Pinned 4.3.4 client rune costs: Icy Touch 45477 one Frost rune, Plague
--     Strike 45462 one Unholy rune, Death Strike 49998 one Frost and one
--     Unholy. Each disease refresh therefore takes half of a Death Strike.
--     Both rows have min_ready_runes 1 and fire as soon as one rune is ready;
--     Death Strike's min_ready_runes 2 gate then fails.
--   * Where a Death Strike landed just before the seize (kills 1-3), Mangle's
--     opening hit landed 42-48k against the 76-113k expected at full armor,
--     consistent with its Blood Shield absorbing about half.
--
-- Change. Icy Touch 45477 and Plague Strike 45462 gain forbidden_self_aura
-- 78412, the Mangle seat aura. boss_magmaw.cpp PassengerBoarded applies it
-- in every mode when the target boards seat 2 and removes it on release.
-- Outside Mangle both rows are unchanged. Frost Fever and Blood Plague may
-- lapse during a hold of up to 30 s; the tank refreshes them after release.
-- No rune, aura, damage or cooldown is manufactured; Death Strike keeps every
-- native gate.
--
-- The migration is idempotent. The row update only changes unrestricted
-- Icy Touch and Plague Strike rows. The version bump never lowers the
-- version. The reverse migration is a commented block at the end of this
-- file, not a separate file: the worldserver auto-updater applies every file
-- in sql/custom/world at startup, so a separate revert file would undo this
-- one immediately.

UPDATE `bot_rotation_action`
SET `forbidden_self_aura` = 78412
WHERE `profile_id` IN (
    SELECT `id` FROM `bot_rotation_profile`
    WHERE `class_id` = 6
      AND `spec_tag` = 'blood_death_knight'
      AND `role` = 'tank'
  )
  AND `spell_id` IN (45477, 45462)
  AND `required_self_aura` = 0
  AND `forbidden_self_aura` = 0;

UPDATE `bot_rotation_profile`
SET `version` = CASE WHEN `version` < 28 THEN 28 ELSE `version` END,
    `source_note` = 'phase9_blood_mangle_disease_runes_2026_09_23',
    `scope_note` = 'Hold Heart Strike, Icy Touch and Plague Strike while the Magmaw Mangle seat aura 78412 is up so Death Strike gets the runes'
WHERE `class_id` = 6
  AND `spec_tag` = 'blood_death_knight'
  AND `role` = 'tank';

-- BEGIN REVERSE MIGRATION
-- UPDATE `bot_rotation_action`
-- SET `forbidden_self_aura` = 0
-- WHERE `profile_id` IN (
--     SELECT `id` FROM `bot_rotation_profile`
--     WHERE `class_id` = 6
--       AND `spec_tag` = 'blood_death_knight'
--       AND `role` = 'tank'
--   )
--   AND `spell_id` IN (45477, 45462)
--   AND `required_self_aura` = 0
--   AND `forbidden_self_aura` = 78412;
-- END REVERSE MIGRATION
