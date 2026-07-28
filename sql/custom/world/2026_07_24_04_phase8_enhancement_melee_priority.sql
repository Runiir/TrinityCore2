-- Prioritize Enhancement's high-value melee cooldowns ahead of Maelstrom spenders.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`priority_bucket` = 1,
    `action`.`sort_order` = CASE `action`.`spell_id`
      WHEN 8050 THEN 18
      WHEN 17364 THEN 22
      WHEN 60103 THEN 24
      WHEN 73680 THEN 26
      ELSE `action`.`sort_order`
    END,
    `action`.`damage_weight` = CASE `action`.`spell_id`
      WHEN 17364 THEN 1.35
      WHEN 60103 THEN 1.35
      WHEN 73680 THEN 1.05
      ELSE `action`.`damage_weight`
    END
WHERE `profile`.`class_id` = 7
  AND `profile`.`spec_tag` = 'enhancement'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` IN (8050, 17364, 60103, 73680);
