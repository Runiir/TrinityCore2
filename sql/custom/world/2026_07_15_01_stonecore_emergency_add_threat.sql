-- Establish area threat immediately after emergency taunts on add swarms.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id` = `action`.`profile_id`
SET `action`.`priority_bucket` = CASE
        WHEN `action`.`spell_id` = 26573 THEN 0
        WHEN `action`.`spell_id` = 53595 THEN 1
        ELSE `action`.`priority_bucket`
    END
WHERE `profile`.`class_id` = 2
  AND `profile`.`spec_tag` = 'protection'
  AND `profile`.`role` = 'tank'
  AND `action`.`spell_id` IN (26573, 53595);
