-- Gate friendly Holy Word use on Chakra: Serenity. Without aura 81208 the
-- action remains hostile Holy Word: Chastise and fails against party members.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id` = `action`.`profile_id`
SET `action`.`required_self_aura` = 81208,
    `action`.`mechanic_tags` = 'holy_word_serenity,spot_heal,requires_chakra_serenity'
WHERE `profile`.`class_id` = 5
  AND `profile`.`spec_tag` = 'holy_priest'
  AND `profile`.`role` = 'healer'
  AND `action`.`spell_id` = 88625;
