-- Restore Shadow Embrace's native all-ranks proc definition. The rank-3
-- talent aura (32392) triggers the real target aura through the generic proc
-- engine; no script-side aura or damage injection is needed.
DELETE FROM `spell_proc` WHERE `SpellId` = -32385;

INSERT INTO `spell_proc`
    (`SpellId`, `SchoolMask`, `SpellFamilyName`, `SpellFamilyMask0`,
     `SpellFamilyMask1`, `SpellFamilyMask2`, `ProcFlags`, `SpellTypeMask`,
     `SpellPhaseMask`, `HitMask`, `AttributesMask`, `DisableEffectsMask`,
     `ProcsPerMinute`, `Chance`, `Cooldown`, `Charges`)
VALUES
    (-32385, 0, 5, 0x00000001, 0x00040000, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0);
