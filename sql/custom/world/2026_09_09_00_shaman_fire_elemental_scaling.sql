-- Bind only the Greater Fire Elemental's three native direct damage spells.
-- The ordinary updater may replay this after a deployment's manual apply.
INSERT INTO `spell_script_names` (`spell_id`, `ScriptName`)
SELECT 57984, 'spell_sha_fire_elemental_spell_scaling'
WHERE NOT EXISTS (
  SELECT 1 FROM `spell_script_names`
  WHERE `spell_id` = 57984 AND `ScriptName` = 'spell_sha_fire_elemental_spell_scaling'
);
INSERT INTO `spell_script_names` (`spell_id`, `ScriptName`)
SELECT 12470, 'spell_sha_fire_elemental_spell_scaling'
WHERE NOT EXISTS (
  SELECT 1 FROM `spell_script_names`
  WHERE `spell_id` = 12470 AND `ScriptName` = 'spell_sha_fire_elemental_spell_scaling'
);
INSERT INTO `spell_script_names` (`spell_id`, `ScriptName`)
SELECT 13376, 'spell_sha_fire_elemental_spell_scaling'
WHERE NOT EXISTS (
  SELECT 1 FROM `spell_script_names`
  WHERE `spell_id` = 13376 AND `ScriptName` = 'spell_sha_fire_elemental_spell_scaling'
);
