-- Phase 8 Frost Death Knight Killing Machine reservation.
--
-- Obliterate is already gated on Killing Machine, but Howling Blast can spend
-- its Frost rune and Frost Strike can consume the proc before a paired-rune
-- Obliterate becomes available. Reserve both the proc and next paired runes for
-- Obliterate while preserving the ordinary Masterfrost Howling Blast cycle.

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`forbidden_self_aura` = 51124
WHERE `profile`.`class_id` = 6
  AND `profile`.`spec_tag` = 'frost_death_knight'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` IN (49143, 49184);
