-- Affliction's exact single-target fixture is intentionally close enough for
-- the player-centered Shadowflame cone. Ordinary hostile spells still use the
-- core's native range checks; remove only the old profile-level 12-yard policy
-- floor that forced the bot back out after every Shadowflame cast.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`min_range` = 0
WHERE `profile`.`class_id` = 9
  AND `profile`.`spec_tag` = 'affliction_warlock'
  AND `profile`.`role` = 'dps'
  AND `action`.`target_selector` = 'enemy'
  AND `action`.`min_range` = 12;
