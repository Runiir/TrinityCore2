-- Bind the Glyph of Death Strike spell script to Death Strike (49998).
--
-- Glyph of Death Strike (glyph spell 59336, pinned 4.3.4 client data:
-- effect 0 = 2 (% per 5 runic power), effect 1 = 40 (cap)) is a dummy aura
-- that had no handler in this core, so the glyph did nothing for players or
-- bots. src/server/scripts/Spells/spell_dk_glyphs.cpp adds
-- spell_dk_glyph_of_death_strike (damage-only hook; the runic power is read,
-- never spent; the Rune Weapon copy reads its owner's glyph and runic power).
-- Evidence: Magmaw 10N kill b2-fd4ba456-k4, Blood tank 30002 at 0.80 of WCL
-- with Death Strike 16.8% of its damage (TANK-002).
--
-- Idempotent; the reverse block is commented at the end because the world
-- auto-updater applies every file in sql/custom/world at startup.

INSERT INTO `spell_script_names` (`spell_id`, `ScriptName`)
SELECT 49998, 'spell_dk_glyph_of_death_strike'
WHERE NOT EXISTS (
    SELECT 1 FROM `spell_script_names`
    WHERE `spell_id` = 49998 AND `ScriptName` = 'spell_dk_glyph_of_death_strike'
);

-- Reverse (apply by hand, then read the row back):
-- DELETE FROM `spell_script_names`
-- WHERE `spell_id` = 49998 AND `ScriptName` = 'spell_dk_glyph_of_death_strike';
