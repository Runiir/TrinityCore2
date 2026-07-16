-- The pinned WoWSims P4 Enhancement APL keeps Searing Totem active.  Using
-- Fire Elemental Totem in this profile replaces Searing and prevents Searing
-- Flames from stacking for Improved Lava Lash, which is a net loss in the
-- measured 4.3.4 implementation.  Keep Fire Elemental available to the bot,
-- but do not select it in the normal single-target/AoE priority profile.

DELETE `action` FROM `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id`=`action`.`profile_id`
WHERE `profile`.`class_id`=7 AND `profile`.`spec_tag`='enhancement' AND `profile`.`role`='dps'
  AND `action`.`spell_id`=2894;

UPDATE `bot_rotation_profile`
SET `version`=8,
    `source_note`='wowsims_p4_searing_totem_priority_2026_07_17',
    `scope_note`='Enhancement priority with Searing Flames feeding Improved Lava Lash'
WHERE `class_id`=7 AND `spec_tag`='enhancement' AND `role`='dps';
