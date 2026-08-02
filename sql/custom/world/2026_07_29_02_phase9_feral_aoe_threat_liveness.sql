-- Phase 9 Feral Druid tank multi-target threat liveness.
--
-- The current-identity second serial canary cleared all 14 Stonecore route
-- nodes, but Feral retained 89.71% of identity-scoped hostiles, eleven samples
-- below the unchanged 90% gate. High Priestess Azil accounted for the shortfall:
-- bucket-0 Growl and Berserk could consume density decisions while Thrash
-- remained bucket 2 and Swipe bucket 3. Promote the two real area actions and
-- retain their two-hostile gate so the single-target rotation is unchanged.

SET @feral_tank_profile := (
    SELECT `id`
    FROM `bot_rotation_profile`
    WHERE `class_id` = 11
      AND `spec_tag` = 'feral_druid_tank'
      AND `role` = 'tank'
    LIMIT 1
);

UPDATE `bot_rotation_action`
SET `priority_bucket` = 0,
    `threat_weight` = GREATEST(`threat_weight`, 2.50),
    `min_enemies` = GREATEST(`min_enemies`, 2),
    `max_enemies` = 0,
    `enabled` = 1
WHERE `profile_id` = @feral_tank_profile
  AND `spell_id` IN (779, 77758);

UPDATE `bot_rotation_action`
SET `priority_bucket` = 1
WHERE `profile_id` = @feral_tank_profile
  AND `spell_id` IN (50334, 6795);

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 5),
    `source_note` = 'phase9_feral_aoe_threat_liveness_2026_07_29',
    `scope_note` = 'Use Thrash and Swipe before single-target actions whenever at least two hostiles are present'
WHERE `id` = @feral_tank_profile;
