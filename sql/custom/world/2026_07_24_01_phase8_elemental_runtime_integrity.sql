-- Make Elemental's declared spender reachable only at Fulmination charge depth.
-- This preserves Lightning Bolt as the filler while ensuring Earth Shock is a
-- real rotation action instead of an unreachable lower-priority fallback.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id` = `action`.`profile_id`
SET `action`.`priority_bucket` = 1,
    `action`.`required_self_aura` = 324,
    `action`.`required_self_aura_stacks` = 7,
    `action`.`mechanic_tags` = 'earth_shock,fulmination,spender'
WHERE `profile`.`class_id` = 7
  AND `profile`.`spec_tag` = 'elemental_shaman'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 8042;
