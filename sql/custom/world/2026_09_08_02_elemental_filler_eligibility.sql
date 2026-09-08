-- 2026_07_24_03_phase8_elemental_aoe_builder_gate.sql intentionally capped
-- Lightning Bolt at one enemy so Chain Lightning covered the multi-target
-- branch.  Keep the enabled Elemental DPS filler available when that area
-- action is unavailable, including the two-enemy fallback case.
--
-- This changes only the stale enemy-count upper bound.  Native range, action
-- priority, area suppression, cooldown/aura, resource, and target checks stay
-- authoritative in the production consumer.
UPDATE `bot_rotation_action`
SET `max_enemies` = 0
WHERE `profile_id` IN (
  SELECT `profile`.`id`
  FROM `bot_rotation_profile` AS `profile`
  WHERE `profile`.`class_id` = 7
    AND `profile`.`spec_tag` = 'elemental_shaman'
    AND `profile`.`role` = 'dps'
    AND `profile`.`enabled` = 1
)
  AND `spell_id` = 403
  AND `enabled` = 1;
