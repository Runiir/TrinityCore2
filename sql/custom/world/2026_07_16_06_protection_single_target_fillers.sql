-- Dummy calibration exposed idle single-target GCDs in the Protection
-- profile.  Consecration and Holy Wrath are legal Cataclysm fillers after
-- Judgement when the core Holy Power actions are unavailable; their existing
-- higher-priority multi-target ordering remains unchanged for two or more
-- engaged hostiles.

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id`=`action`.`profile_id`
SET `action`.`min_enemies`=1,
    `action`.`priority_bucket`=CASE
      WHEN `action`.`spell_id`=26573 THEN 5
      WHEN `action`.`spell_id`=2812 THEN 6
      ELSE `action`.`priority_bucket` END,
    `action`.`mechanic_tags`=CASE
      WHEN `action`.`spell_id`=26573 THEN 'consecration,aoe_threat,single_target_filler'
      WHEN `action`.`spell_id`=2812 THEN 'holy_wrath,aoe_threat,single_target_filler'
      ELSE `action`.`mechanic_tags` END
WHERE `profile`.`class_id`=2 AND `profile`.`spec_tag`='protection' AND `profile`.`role`='tank'
  AND `action`.`spell_id` IN (26573,2812);

UPDATE `bot_rotation_profile`
SET `version`=7,
    `source_note`='dummy_calibration_single_target_fillers_2026_07_16',
    `scope_note`='Guide-aligned Holy Power priority with Consecration and Holy Wrath idle-GCD fillers'
WHERE `class_id`=2 AND `spec_tag`='protection' AND `role`='tank';
