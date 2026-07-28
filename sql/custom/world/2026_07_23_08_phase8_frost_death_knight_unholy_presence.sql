-- Phase 8 Frost Death Knight Masterfrost presence tuning.
--
-- The pinned dual-wield Masterfrost APL opens in Unholy Presence. The original
-- explicit runtime profile forced Frost Presence instead, reducing haste and
-- rune regeneration below the simulator reference conditions.

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`spell_id` = 48265,
    `action`.`mechanic_tags` = 'unholy_presence,self,masterfrost,haste,rune_regeneration',
    `action`.`maintain_aura_id` = 48265
WHERE `profile`.`class_id` = 6
  AND `profile`.`spec_tag` = 'frost_death_knight'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 48266;
