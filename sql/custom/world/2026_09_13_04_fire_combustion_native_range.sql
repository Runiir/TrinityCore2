-- DPS-052: Combustion 11129 uses native SpellRange row 5 (40 yards).
-- db67e88cc8: Fire 30006's dot-ready, LOS-valid opportunity at 37.7469 yd
-- was rejected by its stale 35-yard action cap. Spell.dbc SHA-256:
-- 088a14963d3f81a10963702c760215f49ff73132bea751306c57aae0dae9f39f.
-- Correct every stale matching action, including disabled duplicates, across
-- enabled Fire DPS profiles. Integer FLOAT values are exact and replay-safe.
UPDATE `bot_rotation_action`
SET `max_range` = 40
WHERE `profile_id` IN (
    SELECT `id`
    FROM `bot_rotation_profile`
    WHERE `class_id` = 8
      AND `spec_tag` = 'fire'
      AND `role` = 'dps'
      AND `enabled` = 1
  )
  AND `spell_id` = 11129
  AND `max_range` = 35;
