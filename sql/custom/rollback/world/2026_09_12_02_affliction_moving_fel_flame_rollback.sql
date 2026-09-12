DELETE FROM `bot_rotation_action`
WHERE `profile_id` IN (
  SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 9 AND `spec_tag` = 'affliction_warlock'
    AND `role` = 'dps' AND `enabled` = 1
)
  AND `spell_id` = 77799
  AND `mechanic_tags` = 'fel_flame,moving_filler_20260912';
