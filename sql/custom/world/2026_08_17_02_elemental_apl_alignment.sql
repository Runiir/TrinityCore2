-- Align the Elemental combat profile with the pinned WoWSims Cataclysm APL.
-- Source: WoWSims cata revision
-- 70d87383a9b92f30fb9e370c4676d3ce33b6e6b6, APL SHA256
-- cdc73e0dac1a773a252ccb9eaadb35452e721a210af7b81e38d7b2c7d55d19a9.
--
-- The simulator emits 66843 for its Fire Elemental action but guards it with
-- spellCanCast(2894); 2894 is the actual Trinity castable Fire Elemental
-- Totem spell.  The native combat-totem setup already owns Searing Totem
-- (3599), so it is deliberately not duplicated in this profile.
--
-- The generic profile schema has no target-aura remaining-time predicate.  A
-- required Flame Shock aura plus the APL's <=2-target gate is the narrowest
-- representable Lava Burst admission; the native cooldown and range checks
-- remain authoritative.

DELETE `action`
FROM `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id` = `action`.`profile_id`
WHERE `profile`.`class_id` = 7
  AND `profile`.`spec_tag` = 'elemental_shaman'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` IN (2894, 51505);

INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`, `damage_weight`,
 `priority_bucket`, `min_enemies`, `max_enemies`, `required_target_aura`,
 `target_selector`, `movement_directive`, `auto_attack_mode`, `min_range`, `max_range`)
VALUES
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id` = 7 AND `spec_tag` = 'elemental_shaman' AND `role` = 'dps'), 5, 2894, 'offensive_cooldown', 'fire_elemental_totem,opener,long_cooldown,wowsims_66843', 1.35, 0, 1, 1, 0, 'self', 'ranged', 'none', 0, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id` = 7 AND `spec_tag` = 'elemental_shaman' AND `role` = 'dps'), 15, 51505, 'builder', 'lava_burst,flame_shock_required,pinned_apl', 1.00, 1, 1, 2, 8050, 'enemy', 'ranged', 'none', 12, 35);
