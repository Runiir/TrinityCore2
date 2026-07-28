-- Phase 8 Demonology Warlock Impending Doom cooldown contract.
--
-- Impending Doom uses its flat-modifier aura as the proc surface and stores
-- the 15-second Metamorphosis reduction in its second spell effect. Bind the
-- full talent rank chain to the server-side AuraScript that applies it.

DELETE FROM `spell_script_names`
WHERE `ScriptName` = 'spell_warl_impending_doom';

INSERT INTO `spell_script_names` (`spell_id`, `ScriptName`) VALUES
(-85106, 'spell_warl_impending_doom');

-- The client effect mask only describes the passive Metamorphosis modifier,
-- not the four damage spells that can trigger the cooldown reduction. Override
-- the generated proc mask with Shadow Bolt, Hand of Gul'dan, Incinerate, and
-- Soul Fire while retaining each rank's client proc chance and proc flags.
DELETE FROM `spell_proc`
WHERE `SpellId` = -85106;

INSERT INTO `spell_proc`
    (`SpellId`, `SpellFamilyName`, `SpellFamilyMask0`, `SpellFamilyMask1`,
     `SpellTypeMask`, `SpellPhaseMask`)
VALUES
    (-85106, 5, 0x00200001, 0x000000C0, 0x1, 0x2);
