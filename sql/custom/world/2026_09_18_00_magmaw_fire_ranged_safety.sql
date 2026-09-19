-- Keep Fire Mage offensive casts in a real ranged lane.
--
-- Evidence: the normal Magmaw 10N canary recorded
-- `ranged_damage_too_close` for fire_mage guid 30007 at 7.254 yd in
-- bwd.magmaw.chainwielder and 7.734 yd in bwd.magmaw.encounter.  The active
-- Fire profile had min_range=0 and every hostile action inherited min_range=0,
-- so the native range mover had no reason to create separation.  A 12-yard
-- candidate removed the warning but cost Fire uptime in the matched canary,
-- so this revision uses the smallest 9-yard floor above the 8-yard diagnostic
-- threshold.  The profile remains native-spell-authoritative.

UPDATE `bot_rotation_profile`
SET `min_range` = 9,
    `version` = 3
WHERE `class_id` = 8
  AND `spec_tag` = 'fire'
  AND `role` = 'dps'
  AND `enabled` = 1
  AND `min_range` = 0;

UPDATE `bot_rotation_action`
SET `min_range` = 9,
    `mechanic_tags` = CONCAT(`mechanic_tags`, ',magmaw_ranged_safety_20260918')
WHERE `profile_id` IN (
    SELECT `id`
    FROM `bot_rotation_profile`
    WHERE `class_id` = 8
      AND `spec_tag` = 'fire'
      AND `role` = 'dps'
      AND `enabled` = 1
  )
  AND `enabled` = 1
  AND `target_selector` IN ('enemy', 'ground_enemy')
  AND `max_range` > 0
  AND `min_range` = 0;
