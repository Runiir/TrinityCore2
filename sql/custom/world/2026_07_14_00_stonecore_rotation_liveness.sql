-- Stonecore 5N runtime liveness corrections observed in certified run 073.
UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`target_selector` = 'self'
WHERE p.`class_id` = 2 AND p.`spec_tag` = 'protection' AND p.`role` = 'tank'
  AND a.`spell_id` = 498;

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`damage_weight` = 0.55, a.`min_enemies` = 5
WHERE p.`class_id` = 8 AND p.`spec_tag` = 'fire' AND p.`role` = 'dps'
  AND a.`spell_id` = 2120;

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`required_target_aura` = 1978
WHERE p.`class_id` = 3 AND p.`spec_tag` = 'marksmanship' AND p.`role` = 'dps'
  AND a.`spell_id` = 53209;
