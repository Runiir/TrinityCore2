-- Survival admission only, closed source8146a06b40, profile274/version17.
-- Pinned Spell.dbc 088a14963d3f81a10963702c760215f49ff73132bea751306c57aae0dae9f39f:
-- shots below use native Range197 (40 yd), Kill Shot Range155 (45 yd).
-- Native spell range remains the upper authority. Core single-target shots
-- remain usable with nearby adds; enemy count is not a ban in the pinned SV APL.
-- Integer setters are exact under MySQL FLOAT and idempotent. No weights,
-- minimum ranges, traps, utility, or AoE density gates change.
UPDATE `bot_rotation_profile`
SET `max_range` = 40
WHERE `class_id` = 3 AND `spec_tag` = 'survival'
  AND `role` = 'dps' AND `enabled` = 1;

UPDATE `bot_rotation_action`
SET `max_range` = CASE WHEN `spell_id` = 53351 THEN 45 ELSE 40 END
WHERE `profile_id` IN (
  SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 3 AND `spec_tag` = 'survival'
    AND `role` = 'dps' AND `enabled` = 1
) AND `spell_id` IN (75, 1978, 2643, 3044, 3674, 53301, 77767, 53351);

UPDATE `bot_rotation_action`
SET `max_enemies` = 0
WHERE `profile_id` IN (
  SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 3 AND `spec_tag` = 'survival'
    AND `role` = 'dps' AND `enabled` = 1
) AND `spell_id` IN (53301, 3674, 3044);
