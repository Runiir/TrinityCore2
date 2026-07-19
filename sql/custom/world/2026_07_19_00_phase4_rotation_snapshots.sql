-- Phase 4 immutable rotation-snapshot schema and typed predicates.
-- Pre-migration canonical identity:
--   aggregate SHA-256 7d4adf8b347cbc8d4754fe02f41988982a10cfe077edd7ac816827eb6477c4c7
--   31 enabled profiles, 260 enabled actions
-- Exact per-profile hashes and canonicalization are checked in at
-- experiments/configs/all_spec_phase4_previous_profile_hashes_v1.json.
-- mechanic_tags remain descriptive; runtime gates use only typed columns.

ALTER TABLE `bot_rotation_action`
  ADD COLUMN IF NOT EXISTS `max_self_aura_stacks` TINYINT UNSIGNED NOT NULL DEFAULT 0 AFTER `required_self_aura_stacks`,
  ADD COLUMN IF NOT EXISTS `min_self_aura_remaining_ms` INT UNSIGNED NOT NULL DEFAULT 0 AFTER `max_self_aura_stacks`,
  ADD COLUMN IF NOT EXISTS `max_self_aura_remaining_ms` INT UNSIGNED NOT NULL DEFAULT 0 AFTER `min_self_aura_remaining_ms`,
  ADD COLUMN IF NOT EXISTS `required_owned_target_aura` INT UNSIGNED NOT NULL DEFAULT 0 AFTER `max_self_aura_remaining_ms`,
  ADD COLUMN IF NOT EXISTS `forbidden_owned_target_aura` INT UNSIGNED NOT NULL DEFAULT 0 AFTER `required_owned_target_aura`,
  ADD COLUMN IF NOT EXISTS `min_combo_points` TINYINT UNSIGNED NOT NULL DEFAULT 0 AFTER `forbidden_owned_target_aura`,
  ADD COLUMN IF NOT EXISTS `max_combo_points` TINYINT UNSIGNED NOT NULL DEFAULT 0 AFTER `min_combo_points`,
  ADD COLUMN IF NOT EXISTS `min_ready_runes` TINYINT UNSIGNED NOT NULL DEFAULT 0 AFTER `max_combo_points`,
  ADD COLUMN IF NOT EXISTS `required_shapeshift_form` TINYINT UNSIGNED NOT NULL DEFAULT 0 AFTER `min_ready_runes`,
  ADD COLUMN IF NOT EXISTS `requires_pet` TINYINT UNSIGNED NOT NULL DEFAULT 0 AFTER `required_shapeshift_form`,
  ADD COLUMN IF NOT EXISTS `forbids_pet` TINYINT UNSIGNED NOT NULL DEFAULT 0 AFTER `requires_pet`,
  ADD COLUMN IF NOT EXISTS `required_main_hand_enchant` INT UNSIGNED NOT NULL DEFAULT 0 AFTER `forbids_pet`,
  ADD COLUMN IF NOT EXISTS `required_off_hand_enchant` INT UNSIGNED NOT NULL DEFAULT 0 AFTER `required_main_hand_enchant`,
  ADD COLUMN IF NOT EXISTS `cooldown_group` VARCHAR(64) NOT NULL DEFAULT '' AFTER `required_off_hand_enchant`,
  ADD COLUMN IF NOT EXISTS `target_creature_type_mask` INT UNSIGNED NOT NULL DEFAULT 0 AFTER `cooldown_group`,
  ADD COLUMN IF NOT EXISTS `requires_ground_target` TINYINT UNSIGNED NOT NULL DEFAULT 0 AFTER `target_creature_type_mask`;

-- Owned maintenance gates prevent another caster's disease/debuff from
-- suppressing this bot's application. Refresh-window actions retain their
-- existing typed maintain_aura_id/refresh_aura_below_ms behavior.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id` = `action`.`profile_id`
SET `action`.`forbidden_owned_target_aura` = `action`.`maintain_aura_id`
WHERE `profile`.`enabled` = 1 AND `action`.`enabled` = 1
  AND `action`.`target_selector` = 'enemy'
  AND `action`.`maintain_aura_id` <> 0
  AND `action`.`refresh_aura_below_ms` = 0;

-- Combo-point spenders. A zero max remains unbounded.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id` = `action`.`profile_id`
SET `action`.`min_combo_points` = 1
WHERE `profile`.`enabled` = 1 AND `action`.`enabled` = 1
  AND `action`.`spell_id` IN (408, 1079, 1943, 2098, 22568, 5171);

-- Rune readiness for the explicit Cataclysm DK actions in the catalog.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id` = `action`.`profile_id`
SET `action`.`min_ready_runes` = CASE
    WHEN `action`.`spell_id` IN (49020, 49998, 85948) THEN 2
    ELSE 1
  END
WHERE `profile`.`enabled` = 1 AND `action`.`enabled` = 1
  AND `profile`.`class_id` = 6
  AND `action`.`spell_id` IN (45462, 45477, 49020, 49184, 49998, 55090, 77575, 85948);

-- Druid form gates use ShapeshiftForm values: bear=1, cat=3.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id` = `action`.`profile_id`
SET `action`.`required_shapeshift_form` = 1
WHERE `profile`.`class_id` = 11 AND `profile`.`spec_tag` = 'feral_druid_tank'
  AND `action`.`spell_id` IN (6795, 779, 33745, 33878, 77758, 80313);

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id` = `action`.`profile_id`
SET `action`.`required_shapeshift_form` = 3
WHERE `profile`.`class_id` = 11 AND `profile`.`spec_tag` = 'feral_druid_dps'
  AND `action`.`spell_id` IN (1079, 1822, 22568, 33876, 77758);

-- Pet-dependent actions fail explicitly when the pet/ghoul is unavailable.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id` = `action`.`profile_id`
SET `action`.`requires_pet` = 1
WHERE `profile`.`enabled` = 1 AND `action`.`enabled` = 1
  AND `action`.`spell_id` IN (19577, 34026, 63560);

-- Holy Wrath's typed creature gate is demon (bit 2) or undead (bit 5).
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id` = `action`.`profile_id`
SET `action`.`target_creature_type_mask` = 36
WHERE `profile`.`class_id` = 2 AND `action`.`spell_id` = 2812;

-- Flamestrike is represented as an explicit destination-target action. The
-- snapshot loader validates the DBC destination target mask before publication.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id` = `action`.`profile_id`
SET `action`.`target_selector` = 'ground_enemy',
    `action`.`requires_ground_target` = 1
WHERE `profile`.`class_id` = 8 AND `action`.`spell_id` = 2120;
