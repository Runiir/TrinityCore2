-- Keep the execute arbitration order aligned with the pinned Affliction APL.
-- The APL checks Fel Flame (77799) before Drain Soul (1120) so an observed
-- Fel Flame proc is consumed before entering/continuing the Drain Soul
-- channel.  The original profile placed Drain Soul in bucket 8 and Fel Flame
-- in bucket 9, which made Drain Soul win every time both were executable.
-- Preserve the native proc, channel, and execute gates; only correct the
-- player-like priority order.

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`priority_bucket` = 8,
    `action`.`sort_order` = 80
WHERE `profile`.`class_id` = 9
  AND `profile`.`spec_tag` = 'affliction_warlock'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 77799;

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`priority_bucket` = 9,
    `action`.`sort_order` = 90
WHERE `profile`.`class_id` = 9
  AND `profile`.`spec_tag` = 'affliction_warlock'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 1120;
