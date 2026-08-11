-- Phase 8 Demonology Warlock ranged-lane recovery.
--
-- Once the Felguard contract removed the repeated no-pet cast failure, the
-- calibration clone exposed the underlying profile mismatch: every hostile
-- Demonology action requires ranged range, but the profile advertised a zero
-- minimum. When no hostile candidate was legal at the clone's melee spawn, the
-- resolver therefore had no movement range to recover toward.

UPDATE `bot_rotation_profile`
SET `min_range` = 5,
    `max_range` = 35,
    `range_band` = 'ranged',
    `movement_directive` = 'ranged'
WHERE `class_id` = 9
  AND `spec_tag` = 'demonology_warlock'
  AND `role` = 'dps';
