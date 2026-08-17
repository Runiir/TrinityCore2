-- Restore player-like refresh windows for Balance and Feral Druid maintenance
-- actions.
--
-- Phase 4 converted zero-window maintain_aura rows into a permanent
-- forbidden_owned_target_aura gate.  That is appropriate for one-shot
-- debuffs, but it makes Cataclysm DoTs and Savage Roar unrefreshable after the
-- first native application.  WoWSims' pinned Balance and Feral APLs refresh
-- these effects as part of their combat rotation.  Keep the native aura and
-- owner checks, and admit a refresh only in the final 3 seconds of the aura.
-- This is a policy window, not damage-derived tuning.

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id` = `action`.`profile_id`
SET `action`.`forbidden_owned_target_aura` = 0,
    `action`.`refresh_aura_below_ms` = 3000
WHERE `profile`.`class_id` = 11
  AND `profile`.`spec_tag` = 'balance_druid'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` IN (8921, 5570, 93402);

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id` = `action`.`profile_id`
SET `action`.`forbidden_owned_target_aura` = 0,
    `action`.`refresh_aura_below_ms` = 3000
WHERE `profile`.`class_id` = 11
  AND `profile`.`spec_tag` = 'feral_druid_dps'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` IN (1822, 1079, 33876, 52610);
