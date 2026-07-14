-- Prayer of Mending (33076) applies aura 41635. Avoid repeatedly casting it
-- while the active prayer is already reserved on the tank.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id` = `action`.`profile_id`
SET `action`.`forbidden_target_aura` = 41635,
    `action`.`maintain_aura_id` = 41635
WHERE `profile`.`class_id` = 5
  AND `profile`.`spec_tag` IN ('holy_priest', 'discipline_priest')
  AND `profile`.`role` = 'healer'
  AND `action`.`spell_id` = 33076;
