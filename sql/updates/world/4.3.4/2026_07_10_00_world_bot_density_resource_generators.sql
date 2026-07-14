UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`category` = 'resource_generator'
WHERE (p.`class_id` = 3 AND p.`spec_tag` = 'marksmanship' AND p.`role` = 'dps' AND a.`spell_id` = 56641)
   OR (p.`class_id` = 7 AND p.`spec_tag` = 'enhancement' AND p.`role` = 'dps' AND a.`spell_id` = 17364);
