DELETE FROM `bot_rotation_action`
WHERE `profile_id` IN (
  SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 7
    AND `spec_tag` = 'elemental_shaman'
    AND `role` = 'dps'
    AND `enabled` = 1
)
  AND `spell_id` = 79206
  AND `mechanic_tags` = 'unblock_moving_lava_burst';
