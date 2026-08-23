-- Permit strict-priority clipping only for the Affliction Drain Soul channel.
-- The runtime requires this declarative tag before it can bypass already_casting.

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`mechanic_tags` = CONCAT_WS(',', `action`.`mechanic_tags`, 'interruptible_channel')
WHERE `profile`.`class_id` = 9
  AND `profile`.`spec_tag` = 'affliction_warlock'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 1120
  AND FIND_IN_SET('interruptible_channel', `action`.`mechanic_tags`) = 0;
