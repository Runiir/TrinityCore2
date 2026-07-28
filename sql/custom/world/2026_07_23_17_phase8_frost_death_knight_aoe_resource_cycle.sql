-- Phase 8 Frost Death Knight AoE resource-cycle recovery.
--
-- The tuning107 AoE campaign exposed that the profile's self buffs, cooldowns,
-- Obliterate, Frost Strike, and fallback resource actions were restricted to one
-- enemy. Against the eight-target calibration pack, only Howling Blast remained
-- eligible, leaving runic power capped for the entire scored window. Permit the
-- existing Masterfrost cycle at any enemy count while preserving Howling Blast
-- as the authoritative AoE action through its lower priority bucket and AoE
-- category score.

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`max_enemies` = 0
WHERE `profile`.`class_id` = 6
  AND `profile`.`spec_tag` = 'frost_death_knight'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` IN (
      42650, -- Army of the Dead
      45529, -- Blood Tap
      46584, -- Raise Dead
      47568, -- Empower Rune Weapon
      48266, -- Frost Presence
      49020, -- Obliterate
      49143, -- Frost Strike
      51271, -- Pillar of Frost
      57330, -- Horn of Winter
      77575  -- Outbreak
  );
