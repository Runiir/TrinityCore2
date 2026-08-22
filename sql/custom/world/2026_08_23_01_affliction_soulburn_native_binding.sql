-- The Affliction profile admits Soul Fire only while the native Soulburn
-- aura is present. Bind the AuraScript and its one-charge proc definition so
-- the native Soul Fire proc consumes that window after the first cast.

DELETE FROM `spell_script_names`
WHERE `spell_id` = 74434 AND `ScriptName` <> 'spell_warl_soulburn';

INSERT INTO `spell_script_names` (`spell_id`, `ScriptName`)
VALUES (74434, 'spell_warl_soulburn')
ON DUPLICATE KEY UPDATE `ScriptName` = VALUES(`ScriptName`);

DELETE FROM `spell_proc` WHERE `SpellId` = 74434;
INSERT INTO `spell_proc`
    (`SpellId`, `SpellFamilyName`, `SpellFamilyMask0`, `SpellFamilyMask1`,
     `SpellFamilyMask2`, `ProcFlags`, `SpellTypeMask`, `SpellPhaseMask`,
     `HitMask`, `AttributesMask`, `Cooldown`, `Charges`, `Chance`)
VALUES
    (74434, 5,
     0x00000100 | 0x20000000 | 0x00000008 | 0x00010000,
     0x00000080 | 0x00000010,
     0x00008000,
     0x00010000 | 0x00004000 | 0x00000400,
     7, 1, 0, 0, 0, 1, 100);
