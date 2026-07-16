-- Bots submit server-side spell casts rather than client action-bar buttons.
-- Use the friendly Serenity spell directly while retaining the exact Chakra:
-- Serenity aura gate established by the preceding migration.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id` = `action`.`profile_id`
SET `action`.`spell_id` = 88684,
    `action`.`mechanic_tags` = 'holy_word_serenity,spot_heal,requires_chakra_serenity'
WHERE `profile`.`class_id` = 5
  AND `profile`.`spec_tag` = 'holy_priest'
  AND `profile`.`role` = 'healer'
  AND `action`.`spell_id` = 88625;
