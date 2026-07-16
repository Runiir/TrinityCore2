-- Run 226 confirmed that forcing an Unleash Elements setup GCD before every
-- Flame Shock refresh reduces total live-engine throughput despite matching
-- the simulator APL.  Preserve the stronger measured ordering from run 225:
-- Flame Shock maintains full uptime, while Unleash Elements remains a lower
-- priority damage action and naturally buffs Flame Shock when timings align.

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id`=`action`.`profile_id`
SET `action`.`priority_bucket`=4,
    `action`.`sort_order`=65,
    `action`.`damage_weight`=0.84,
    `action`.`mechanic_tags`='unleash_elements,damage'
WHERE `profile`.`class_id`=7 AND `profile`.`spec_tag`='enhancement' AND `profile`.`role`='dps'
  AND `action`.`spell_id`=73680;

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id`=`action`.`profile_id`
SET `action`.`priority_bucket`=1,
    `action`.`required_self_aura`=0,
    `action`.`maintain_aura_id`=8050,
    `action`.`refresh_aura_below_ms`=0,
    `action`.`mechanic_tags`='flame_shock,dot,maintain_full_uptime'
WHERE `profile`.`class_id`=7 AND `profile`.`spec_tag`='enhancement' AND `profile`.`role`='dps'
  AND `action`.`spell_id`=8050;

UPDATE `bot_rotation_profile`
SET `version`=10,
    `source_note`='calibration_run_226_unleash_flame_rollback_2026_07_17',
    `scope_note`='Measured live priority: Searing Flames, full Flame Shock uptime, lower-priority Unleash Elements'
WHERE `class_id`=7 AND `spec_tag`='enhancement' AND `role`='dps';
