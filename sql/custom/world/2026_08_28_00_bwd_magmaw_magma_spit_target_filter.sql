-- Keep Magma Spit's native target selection and 78359 damage intact.
-- The missile's destination-area damage must only resolve against the unit
-- explicitly selected by the targeting spell.
DELETE FROM `spell_script_names`
WHERE `spell_id` = 78359
  AND `ScriptName` <> 'spell_magmaw_magma_spit_missile';

INSERT INTO `spell_script_names` (`spell_id`, `ScriptName`)
VALUES (78359, 'spell_magmaw_magma_spit_missile')
ON DUPLICATE KEY UPDATE `ScriptName` = VALUES(`ScriptName`);
