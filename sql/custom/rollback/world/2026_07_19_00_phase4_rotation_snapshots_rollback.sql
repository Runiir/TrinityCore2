-- Controlled restore payload for 2026_07_19_00_phase4_rotation_snapshots.sql.
-- Restores the only pre-existing column changed by the forward migration, then
-- removes the Phase 4 typed columns. The expected restored content identity is
-- 7d4adf8b347cbc8d4754fe02f41988982a10cfe077edd7ac816827eb6477c4c7;
-- exact per-profile hashes are in
-- experiments/configs/all_spec_phase4_previous_profile_hashes_v1.json.

UPDATE `bot_rotation_action`
SET `category` = 'control'
WHERE `enabled` = 1 AND `category` = 'stun_cc' AND `spell_id` = 408;

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id` = `action`.`profile_id`
SET `action`.`target_selector` = 'enemy'
WHERE `profile`.`class_id` = 8 AND `action`.`spell_id` = 2120
  AND `action`.`target_selector` = 'ground_enemy';

ALTER TABLE `bot_rotation_action`
  DROP COLUMN IF EXISTS `requires_ground_target`,
  DROP COLUMN IF EXISTS `target_creature_type_mask`,
  DROP COLUMN IF EXISTS `cooldown_group`,
  DROP COLUMN IF EXISTS `required_off_hand_enchant`,
  DROP COLUMN IF EXISTS `required_main_hand_enchant`,
  DROP COLUMN IF EXISTS `forbids_pet`,
  DROP COLUMN IF EXISTS `requires_pet`,
  DROP COLUMN IF EXISTS `required_shapeshift_form`,
  DROP COLUMN IF EXISTS `min_ready_runes`,
  DROP COLUMN IF EXISTS `max_combo_points`,
  DROP COLUMN IF EXISTS `min_combo_points`,
  DROP COLUMN IF EXISTS `forbidden_owned_target_aura`,
  DROP COLUMN IF EXISTS `required_owned_target_aura`,
  DROP COLUMN IF EXISTS `max_self_aura_remaining_ms`,
  DROP COLUMN IF EXISTS `min_self_aura_remaining_ms`,
  DROP COLUMN IF EXISTS `max_self_aura_stacks`;
