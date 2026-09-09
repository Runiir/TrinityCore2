-- Restore the prior Wild Quiver CAST phase without changing other proc fields.
UPDATE `spell_proc` SET `SpellPhaseMask` = 1
WHERE `SpellID` = 76659 AND `SpellPhaseMask` = 2;
