-- Atramedes (41442): Devastation hits only the player whose Sound reached 100.
--
-- Staged, not auto-applied: the coordinator moves this file to
-- sql/custom/world after review (every file there is applied at startup).
--
-- Native chain (boss_atramedes.cpp, boss_atramedes_spells.cpp):
--   spell_atramedes_sound_bar casts Noisy! (78897, 30 s) on a player at
--   maximum alternate power and adds them to Atramedes' noisy set;
--   spell_atramedes_devastation_trigger lets Devastation Trigger (78898,
--   500 ms) fire Devastation (78868) only while that set is non-empty.
-- Defect: Devastation's only effect targets TARGET_SRC_CASTER +
-- TARGET_UNIT_SRC_AREA_ENEMY with a 50,000 yd radius (4.3.4 Spell.dbc /
-- SpellEffect.dbc and the 4.4.2.59185 client rows agree) and the world DB
-- has no condition on it. Once any player is Noisy, every player takes
-- 24,374 Fire (25N 24,374, heroic 29,249) twice a second: a raid wipe.
--
-- Sources for the intended target (retrieved 2026-09-25):
--   Wowhead, "Atramedes Strategy Guide - Blackwing Descent Raid Cataclysm
--   Classic" (updated 2024-06-04): "if allowed to reach 100, Atramedes will
--   cast its deadly Devastation ability on the located player".
--   Icy Veins, "Atramedes Encounter Guide: Strategy, Abilities, Loot -
--   Cataclysm Classic" (Abide, 2024-07-29): "If a player reaches 100 sound,
--   Atramedes will cast Devastation on them, instantly killing them."
--
-- Fix: restrict effect 0 of Devastation and its difficulty variants
-- (SpellDifficulty 3134: 78868, 92460, 92461, 92462) to units carrying
-- Noisy! effect 0 (CONDITION_AURA). Spell values are unchanged.
-- Idempotent. The reverse migration is the commented block at the end.

DELETE FROM `conditions` WHERE `SourceTypeOrReferenceId` = 13 AND `SourceGroup` = 1
    AND `SourceEntry` IN (78868, 92460, 92461, 92462)
    AND `ConditionTypeOrReference` = 1 AND `ConditionValue1` = 78897;
INSERT INTO `conditions` (`SourceTypeOrReferenceId`, `SourceGroup`, `SourceEntry`, `SourceId`, `ElseGroup`,
    `ConditionTypeOrReference`, `ConditionTarget`, `ConditionValue1`, `ConditionValue2`, `ConditionValue3`,
    `NegativeCondition`, `ErrorType`, `ErrorTextId`, `ScriptName`, `Comment`) VALUES
(13, 1, 78868, 0, 0, 1, 0, 78897, 0, 0, 0, 0, 0, '', 'Atramedes - Devastation - Target Noisy player'),
(13, 1, 92460, 0, 0, 1, 0, 78897, 0, 0, 0, 0, 0, '', 'Atramedes - Devastation - Target Noisy player'),
(13, 1, 92461, 0, 0, 1, 0, 78897, 0, 0, 0, 0, 0, '', 'Atramedes - Devastation - Target Noisy player'),
(13, 1, 92462, 0, 0, 1, 0, 78897, 0, 0, 0, 0, 0, '', 'Atramedes - Devastation - Target Noisy player');

-- BEGIN REVERSE MIGRATION
-- DELETE FROM `conditions` WHERE `SourceTypeOrReferenceId` = 13 AND `SourceGroup` = 1
--     AND `SourceEntry` IN (78868, 92460, 92461, 92462)
--     AND `ConditionTypeOrReference` = 1 AND `ConditionValue1` = 78897;
-- END REVERSE MIGRATION
