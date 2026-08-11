-- The pinned Elemental fixture does not accumulate observable Lightning Shield
-- charges during dummy combat, so a Fulmination stack gate makes the declared
-- spender disappear from runtime evidence. Keep Earth Shock in the first ready
-- priority bucket after Flame Shock maintenance instead.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id` = `action`.`profile_id`
SET `action`.`priority_bucket` = 1,
    `action`.`required_self_aura` = 0,
    `action`.`required_self_aura_stacks` = 0,
    `action`.`mechanic_tags` = 'earth_shock,spender,instant'
WHERE `profile`.`class_id` = 7
  AND `profile`.`spec_tag` = 'elemental_shaman'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 8042;
