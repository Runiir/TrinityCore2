-- Complete the parent Tame Beast channel only after its final trigger creates the pet.
DELETE FROM `spell_script_names` WHERE `spell_id` = 13481 AND `ScriptName` = 'spell_hun_tame_beast_completion';
INSERT INTO `spell_script_names` (`spell_id`, `ScriptName`) VALUES (13481, 'spell_hun_tame_beast_completion');
