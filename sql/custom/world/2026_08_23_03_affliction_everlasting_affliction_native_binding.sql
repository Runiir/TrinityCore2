-- Restore the native Everlasting Affliction rank and proc chain. The proc
-- engine applies the 47203 talent rank and invokes the 47422 script.
DELETE FROM `spell_ranks`
WHERE `first_spell_id` = 47201;

INSERT INTO `spell_ranks` (`first_spell_id`, `spell_id`, `rank`) VALUES
(47201, 47201, 1),
(47201, 47202, 2),
(47201, 47203, 3);

-- Preserve the canonical native proc definition for the talent aura.
DELETE FROM `spell_proc` WHERE `SpellId` = -47201;

INSERT INTO `spell_proc`
    (`SpellId`, `SchoolMask`, `SpellFamilyName`, `SpellFamilyMask0`,
     `SpellFamilyMask1`, `SpellFamilyMask2`, `ProcFlags`, `SpellTypeMask`,
     `SpellPhaseMask`, `HitMask`, `AttributesMask`, `DisableEffectsMask`,
     `ProcsPerMinute`, `Chance`, `Cooldown`, `Charges`)
VALUES
    (-47201, 0, 5, 16392, 262144, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0);

-- Register the native trigger that refreshes Corruption.
DELETE FROM `spell_script_names`
WHERE `spell_id` = 47422
  AND `ScriptName` <> 'spell_warl_everlasting_affliction';

INSERT INTO `spell_script_names` (`spell_id`, `ScriptName`)
VALUES (47422, 'spell_warl_everlasting_affliction')
ON DUPLICATE KEY UPDATE `ScriptName` = VALUES(`ScriptName`);
