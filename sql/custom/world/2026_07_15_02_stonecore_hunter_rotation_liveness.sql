-- Hunter's Mark is a pre-pull maintenance action. Keep it below every real
-- rotational shot in combat so a target swap cannot monopolize the GCD while
-- Serpent Sting, Chimera Shot, Aimed Shot, and the focus cycle are available.
UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`priority_bucket` = 6,
    a.`damage_weight` = 0.10
WHERE p.`class_id` = 3
  AND p.`spec_tag` = 'marksmanship'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 1130;
