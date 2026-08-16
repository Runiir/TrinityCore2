-- Reconcile an already-applied Affliction profile with Shadowflame's native
-- self-cast frontal-cone contract. The hostile unit remains the ordinary
-- movement/facing anchor; the core spell is submitted on the player.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`target_selector` = 'self',
    `action`.`movement_directive` = 'ranged',
    `action`.`min_range` = 0,
    `action`.`max_range` = 8
WHERE `profile`.`class_id` = 9
  AND `profile`.`spec_tag` = 'affliction_warlock'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 47897;
