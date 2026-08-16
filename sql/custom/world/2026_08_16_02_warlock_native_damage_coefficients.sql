-- Bind Shadow Bite's target-state mechanic to the native warlock spell script.
-- Soul Fire, Haunt, and Shadow Bite coefficients are corrected in SpellMgr
-- because their Cataclysm SpellEffect rows contain zero coefficients.
DELETE FROM `spell_script_names`
WHERE `spell_id` = 54049 AND `ScriptName` <> 'spell_warl_shadow_bite';

INSERT INTO `spell_script_names` (`spell_id`, `ScriptName`)
VALUES (54049, 'spell_warl_shadow_bite')
ON DUPLICATE KEY UPDATE `ScriptName` = VALUES(`ScriptName`);
