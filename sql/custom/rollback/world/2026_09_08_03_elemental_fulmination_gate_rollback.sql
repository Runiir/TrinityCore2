-- Restore the immediate pre-migration Earth Shock policy, retaining priorities.
UPDATE `bot_rotation_action`
SET `required_self_aura` = 0,
    `required_self_aura_stacks` = 0,
    `max_self_aura_stacks` = 0,
    `required_owned_target_aura` = 0,
    `max_enemies` = 0,
    `mechanic_tags` = 'earth_shock,spender,instant'
WHERE `profile_id` IN (
  SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 7 AND `spec_tag` = 'elemental_shaman'
    AND `role` = 'dps' AND `enabled` = 1
)
  AND `spell_id` = 8042 AND `enabled` = 1;
ALTER TABLE `bot_rotation_action` DROP COLUMN IF EXISTS `min_owned_target_aura_remaining_ms`;
ALTER TABLE `bot_rotation_action` DROP COLUMN IF EXISTS `max_self_aura_charges`;
ALTER TABLE `bot_rotation_action` DROP COLUMN IF EXISTS `required_self_aura_charges`;
