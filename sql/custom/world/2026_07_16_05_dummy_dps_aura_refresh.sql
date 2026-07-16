-- Run 195 showed that Survival applied Serpent Sting once, but Cobra Shot did
-- not keep its periodic damage active for the full dummy window. Use the
-- profile's existing refresh threshold so the rotation repairs the DoT in the
-- last three seconds without clipping healthy ticks.

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id`=`action`.`profile_id`
SET `action`.`forbidden_target_aura`=0,
    `action`.`maintain_aura_id`=1978,
    `action`.`refresh_aura_below_ms`=3000,
    `action`.`mechanic_tags`='serpent_sting,maintain_debuff,refresh_below_3s'
WHERE `profile`.`class_id`=3 AND `profile`.`spec_tag`='survival' AND `profile`.`role`='dps'
  AND `action`.`spell_id`=1978;

UPDATE `bot_rotation_profile`
SET `version`=7, `source_note`='dummy_calibration_run_195_aura_refresh_2026_07_16'
WHERE `class_id`=3 AND `spec_tag`='survival' AND `role`='dps';
