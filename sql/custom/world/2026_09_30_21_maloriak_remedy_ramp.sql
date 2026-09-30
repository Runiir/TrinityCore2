-- Maloriak Remedy heal ramp: bind spell_maloriak_remedy (boss_maloriak_spells.cpp) to Remedy
-- 77912, the 10N id. The 4.3.4 difficulty variants 92965 (25N), 92966 (10H) and 92967 (25H) stay
-- unbound (flat heal): the evidence is 10N only.
--
-- Staged 2026-09-30 (BWD 10N round 3); promotion to sql/custom/world is the coordinator's step.
-- Until it is applied the script is registered but unbound and Remedy stays a flat heal.
--
-- Evidence: WCL VL3fW9wNm2PRJDYt fight 13 (Maloriak 10N kill, 2024-10-21), Maloriak's Remedy
-- heal ticks for the casts at 43.3 s and 64.4 s: 22,500, 45,000, 67,500, 90,000, 112,500,
-- 135,000, 175,000, 180,000 / 200,000, 202,500 / 225,000, 225,000 / 250,000, i.e. 25,000 x the
-- tick number (x 0.9 while a -10% healing debuff was up). The 4.4.2 client row (77912 effect 0,
-- aura 8, 25,000 per 1 s for 10 s) is flat, so the ramp is scripted. Read by GPT-6.1 Sol in the
-- user's Chrome on 2026-09-30 (raw capture ~/.cache/maloriak_wcl_r3/resultG.json).
--
-- The live world DB read back on 2026-09-30 has no spell_script_names row for 77912 or its variants.
-- Idempotent: the DELETE first. The reverse is the commented block at the end.

DELETE FROM `spell_script_names` WHERE `spell_id` = 77912 AND `ScriptName` = 'spell_maloriak_remedy';
INSERT INTO `spell_script_names` (`spell_id`, `ScriptName`) VALUES
(77912, 'spell_maloriak_remedy');

-- BEGIN REVERSE MIGRATION
-- DELETE FROM `spell_script_names` WHERE `spell_id` = 77912 AND `ScriptName` = 'spell_maloriak_remedy';
-- END REVERSE MIGRATION
