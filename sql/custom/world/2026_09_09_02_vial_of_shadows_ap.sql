-- Heroic Vial only: native proc-event AP addition, preserving the DBC trigger.
DELETE FROM `spell_script_names`
WHERE `spell_id` = 109725 AND `ScriptName` = 'spell_item_vial_of_shadows';
INSERT INTO `spell_script_names` (`spell_id`, `ScriptName`)
VALUES (109725, 'spell_item_vial_of_shadows');
