UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`damage_weight` = 0.55,
    a.`priority_bucket` = 6,
    a.`min_enemies` = 5
WHERE p.`class_id` = 8
  AND p.`spec_tag` = 'fire'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 2120;
