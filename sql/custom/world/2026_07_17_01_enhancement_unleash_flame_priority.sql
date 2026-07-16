-- The pinned WoWSims P4 Enhancement APL applies or refreshes Flame Shock only
-- while Unleash Flame is active.  Run 225 still cast every Flame Shock without
-- this gate, leaving measurable periodic damage on the table.  Keep the
-- working Searing Flames / Lava Lash setup and make Unleash Elements prepare
-- Flame Shock before its nine-second refresh window.

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id`=`action`.`profile_id`
SET `action`.`priority_bucket`=1,
    `action`.`sort_order`=18,
    `action`.`damage_weight`=1.10,
    `action`.`mechanic_tags`='unleash_elements,prepare_unleash_flame'
WHERE `profile`.`class_id`=7 AND `profile`.`spec_tag`='enhancement' AND `profile`.`role`='dps'
  AND `action`.`spell_id`=73680;

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id`=`action`.`profile_id`
SET `action`.`priority_bucket`=1,
    `action`.`required_self_aura`=73683,
    `action`.`maintain_aura_id`=8050,
    `action`.`refresh_aura_below_ms`=9000,
    `action`.`mechanic_tags`='flame_shock,dot,requires_unleash_flame,refresh_below_9s'
WHERE `profile`.`class_id`=7 AND `profile`.`spec_tag`='enhancement' AND `profile`.`role`='dps'
  AND `action`.`spell_id`=8050;

UPDATE `bot_rotation_profile`
SET `version`=9,
    `source_note`='wowsims_p4_unleash_flame_priority_2026_07_17',
    `scope_note`='Enhancement priority with Searing Flames and Unleash Flame-gated Flame Shock'
WHERE `class_id`=7 AND `spec_tag`='enhancement' AND `role`='dps';
