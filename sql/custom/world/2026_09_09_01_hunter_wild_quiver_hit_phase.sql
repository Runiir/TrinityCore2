-- Wild Quiver's scripted damage requires the HIT event's action target.
-- CAST events carry no action target. Preserve every other proc setting.
UPDATE `spell_proc` SET `SpellPhaseMask` = 2
WHERE `SpellID` = 76659 AND `SpellPhaseMask` = 1;
