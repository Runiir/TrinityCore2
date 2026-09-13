-- DPS-047: source69903f785e, Survival profile274 action2149.
-- Spell13813 is a self-placed trap (native range0), not a remotely launched
-- ranged AoE. Its ordinary enemy-target row repeatedly requests inward range
-- reconciliation. Keep the separate aura2825 scored opener and all shots.
UPDATE `bot_rotation_action`
SET `enabled` = 0
WHERE `profile_id` IN (
    SELECT `id` FROM `bot_rotation_profile`
    WHERE `class_id` = 3 AND `spec_tag` = 'survival' AND `role` = 'dps'
      AND `enabled` = 1
  )
  AND `spell_id` = 13813
  AND `target_selector` = 'enemy'
  AND `sort_order` = 40
  AND `min_enemies` = 2
  AND `required_self_aura` = 0;
