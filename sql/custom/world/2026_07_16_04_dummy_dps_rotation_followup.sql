-- Follow-up to calibration run 190: retain the successful paladin resource
-- gate, prevent Inquisition refresh waste, and revert the measured Shaman
-- priority regression while keeping the full rotation available.

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id`=`action`.`profile_id`
SET `action`.`maintain_aura_id`=84963,
    `action`.`mechanic_tags`='inquisition,holy_power,multi_target,maintain_aura'
WHERE `profile`.`class_id`=2 AND `profile`.`spec_tag`='protection' AND `profile`.`role`='tank'
  AND `action`.`spell_id`=84963;

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id`=`action`.`profile_id`
SET `action`.`priority_bucket`=4
WHERE `profile`.`class_id`=7 AND `profile`.`spec_tag`='enhancement' AND `profile`.`role`='dps'
  AND `action`.`spell_id`=73680;

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id`=`action`.`profile_id`
SET `action`.`priority_bucket`=1, `action`.`required_self_aura`=0,
    `action`.`mechanic_tags`='flame_shock,dot'
WHERE `profile`.`class_id`=7 AND `profile`.`spec_tag`='enhancement' AND `profile`.`role`='dps'
  AND `action`.`spell_id`=8050;

UPDATE `bot_rotation_profile`
SET `version`=6, `source_note`='dummy_calibration_run_190_followup_2026_07_16'
WHERE (`class_id`=2 AND `spec_tag`='protection' AND `role`='tank')
   OR (`class_id`=8 AND `spec_tag`='fire' AND `role`='dps')
   OR (`class_id`=7 AND `spec_tag`='enhancement' AND `role`='dps');
