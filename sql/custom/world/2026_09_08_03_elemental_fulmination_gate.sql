-- Native Lightning Shield uses Aura charges, not stack amount.
ALTER TABLE `bot_rotation_action`
  ADD COLUMN IF NOT EXISTS `required_self_aura_charges` TINYINT UNSIGNED NOT NULL DEFAULT 0;
ALTER TABLE `bot_rotation_action`
  ADD COLUMN IF NOT EXISTS `max_self_aura_charges` TINYINT UNSIGNED NOT NULL DEFAULT 0;
ALTER TABLE `bot_rotation_action`
  ADD COLUMN IF NOT EXISTS `min_owned_target_aura_remaining_ms` INT UNSIGNED NOT NULL DEFAULT 0;

UPDATE `bot_rotation_action`
SET `required_self_aura` = 324,
    `required_self_aura_stacks` = 0,
    `max_self_aura_stacks` = 0,
    `required_self_aura_charges` = 9,
    `max_self_aura_charges` = 9,
    `required_owned_target_aura` = 8050,
    `min_owned_target_aura_remaining_ms` = 3000,
    `max_enemies` = 1,
    `mechanic_tags` = 'earth_shock,spender,instant,fulmination'
WHERE `profile_id` IN (
  SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 7 AND `spec_tag` = 'elemental_shaman'
    AND `role` = 'dps' AND `enabled` = 1
)
  AND `spell_id` = 8042 AND `enabled` = 1;
