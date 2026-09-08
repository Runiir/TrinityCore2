-- Marksmanship eligibility cap follows the native DBC ranges.
--
-- Evidence: the pinned data/dbc/enUS/Spell.dbc has SHA-256
-- 088a14963d3f81a10963702c760215f49ff73132bea751306c57aae0dae9f39f.
-- Main-shot spells (75, 1978, 53209, 19434, 2643, 3044, 56641) use
-- RangeIndex 197 (40 yd); Kill Shot (53351) uses RangeIndex 155 (45 yd).
-- Only the profile/action eligibility cap changes here.  Native spell
-- legality, minimum ranges, priorities, selectors, and utility actions stay
-- authoritative and unchanged.

UPDATE `bot_rotation_profile`
SET `max_range` = 40
WHERE `class_id` = 3
  AND `spec_tag` = 'marksmanship'
  AND `role` = 'dps'
  AND `enabled` = 1;

UPDATE `bot_rotation_action`
SET `max_range` = CASE
    WHEN `spell_id` = 53351 THEN 45
    ELSE 40
  END
WHERE `profile_id` IN (
    SELECT `id`
    FROM `bot_rotation_profile`
    WHERE `class_id` = 3
      AND `spec_tag` = 'marksmanship'
      AND `role` = 'dps'
      AND `enabled` = 1
  )
  AND `spell_id` IN (75, 1978, 53209, 19434, 2643, 3044, 56641, 53351);
