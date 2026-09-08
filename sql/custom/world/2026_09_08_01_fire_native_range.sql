-- Fire Mage eligibility caps follow the native DBC ranges.
--
-- Evidence: the pinned data/dbc/enUS/Spell.dbc has SHA-256
-- 088a14963d3f81a10963702c760215f49ff73132bea751306c57aae0dae9f39f.
-- Fireball (133) and Living Bomb (44457) use RangeIndex 5 (40 yd); Fire
-- Blast (2136) uses RangeIndex 4 (30 yd). Only the Fire DPS profile and the
-- two affected action eligibility caps change here. Native spell legality,
-- priorities, selectors, and other Fire actions remain authoritative and
-- unchanged; the native 30 yd Fire Blast limit is not widened.

UPDATE `bot_rotation_profile`
SET `max_range` = 40
WHERE `class_id` = 8
  AND `spec_tag` = 'fire'
  AND `role` = 'dps'
  AND `enabled` = 1;

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
  AND `spell_id` IN (133, 44457);
