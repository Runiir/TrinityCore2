-- Native hostile minima for these Elemental spells are zero. The inherited
-- 12-yard action floor makes the bot retreat from otherwise legal targets.
-- Encounter safety movement and native maximum range remain authoritative.
UPDATE `bot_rotation_action`
SET `min_range` = 0,
    `mechanic_tags` = CONCAT(`mechanic_tags`, ',native_min_range_20260912')
WHERE `profile_id` IN (
  SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 7 AND `spec_tag` = 'elemental_shaman'
    AND `role` = 'dps' AND `enabled` = 1
)
  AND `enabled` = 1
  AND `spell_id` IN (8050, 421, 403, 8042, 51505)
  AND `min_range` = 12;
