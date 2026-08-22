-- Restore Shadow Embrace's native all-ranks proc definition. The rank-3
-- talent aura (32392) triggers the real target aura through the generic proc
-- engine; restore the DBC rank chain so the all-ranks proc expands correctly.
-- No script-side aura or damage injection is needed.
DELETE FROM `spell_ranks`
WHERE `first_spell_id` = 32385
   OR `spell_id` IN (32385, 32387, 32392);

INSERT INTO `spell_ranks` (`first_spell_id`, `spell_id`, `rank`) VALUES
    (32385, 32385, 1),
    (32385, 32387, 2),
    (32385, 32392, 3);

DELETE FROM `spell_proc` WHERE `SpellId` = -32385;

INSERT INTO `spell_proc`
    (`SpellId`, `SchoolMask`, `SpellFamilyName`, `SpellFamilyMask0`,
     `SpellFamilyMask1`, `SpellFamilyMask2`, `ProcFlags`, `SpellTypeMask`,
     `SpellPhaseMask`, `HitMask`, `AttributesMask`, `DisableEffectsMask`,
     `ProcsPerMinute`, `Chance`, `Cooldown`, `Charges`)
VALUES
    (-32385, 0, 5, 0x00000001, 0x00040000, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0);
