-- Blood Death Knight tank: no Heart Strike while Magmaw's Mangle holds the
-- tank, so Death Strike gets the runes.
--
-- Evidence, Magmaw 10N, actor 30002 (Mgwtankb). The tank is seized at 90.0 s
-- and released by impale at 107.8-110.0 s.
--   * bundle1-b8a539b kills 1 and 2 (both tank deaths): no Death Strike after
--     88.1 / 88.7 s. The seized tank cast Heart Strike 5 times, at
--     94.6-105.1 s and 93.8-102.5 s. Death Strike failed its ready-rune gate
--     1,807 and 1,829 times (min_ready_runes 2).
--   * Blood Rites 50034 (provisioned) turns the Frost and Unholy runes used by
--     Death Strike into Death runes. One Blood rune pair cannot feed five Heart
--     Strikes in ~11 s, so Heart Strike consumed the Death runes, one at a time,
--     as they came ready. Death Strike never saw two ready runes.
--   * Each Death Strike that did land while seized was followed by 23-64k of
--     absorbed Mangle damage (Blood Shield), and it heals 14,136 (7% of max
--     health). The two deaths had 60k and 40k absorbed in the whole window,
--     against 118-150k in the four survivals.
--
-- Change. Heart Strike 55050 gains forbidden_self_aura 78412. 78412 is the
-- Mangle seat aura. boss_magmaw.cpp PassengerBoarded applies it in every mode
-- when the target boards seat 2, and removes it on release. The seized tank is
-- always missing health: each Mangle tick lands 36-51k at full armor. A
-- health carve-out would let Heart Strike take a Death rune again.
-- Outside Mangle, Heart Strike is unchanged. No rune, aura, damage or
-- cooldown is manufactured; Death Strike keeps every native gate.
--
-- The migration is idempotent. The row update only changes an unrestricted
-- Heart Strike row. The version bump never lowers the version. The reverse
-- migration is a commented block at the end of this file, not a separate
-- file: the worldserver auto-updater applies every file in sql/custom/world
-- at startup, so a separate revert file would undo this one immediately.

UPDATE `bot_rotation_action`
SET `forbidden_self_aura` = 78412
WHERE `profile_id` IN (
    SELECT `id` FROM `bot_rotation_profile`
    WHERE `class_id` = 6
      AND `spec_tag` = 'blood_death_knight'
      AND `role` = 'tank'
  )
  AND `spell_id` = 55050
  AND `required_self_aura` = 0
  AND `forbidden_self_aura` = 0;

UPDATE `bot_rotation_profile`
SET `version` = CASE WHEN `version` < 27 THEN 27 ELSE `version` END,
    `source_note` = 'phase9_blood_mangle_death_strike_runes_2026_09_23',
    `scope_note` = 'Hold Heart Strike while the Magmaw Mangle seat aura 78412 is up so Death Strike gets the Death runes'
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
--   AND `spell_id` = 55050
--   AND `required_self_aura` = 0
--   AND `forbidden_self_aura` = 78412;
-- END REVERSE MIGRATION
