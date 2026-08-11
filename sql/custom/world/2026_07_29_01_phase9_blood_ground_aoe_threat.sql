-- Phase 9 Blood Death Knight distributed area-threat liveness.
--
-- The current-identity serial canary completed all 14 Stonecore route nodes, but
-- Blood retained only 78.22% of identity-scoped hostiles. Blood Boil executed
-- before Death and Decay whenever both were legal because its deterministic
-- candidate score was 6.86 versus 6.55; sort_order is only a tie-break. During
-- the Azil follower wave that delayed persistent ground threat until ownership
-- had fallen from 60/60 to 8/58, while the first Death and Decay tick restored
-- 57/57 ownership. Authorize baseline Death and Decay, score it ahead of Blood
-- Boil, and reserve bucket 0 offensive priority for the two explicit area
-- actions. The demoted actions remain available whenever fewer than two hostiles
-- make both area actions ineligible.

SET @blood_profile := (
    SELECT `id`
    FROM `bot_rotation_profile`
    WHERE `class_id` = 6
      AND `spec_tag` = 'blood_death_knight'
      AND `role` = 'tank'
    LIMIT 1
);

INSERT INTO `bot_rotation_action` (
    `profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
    `damage_weight`, `threat_weight`, `priority_bucket`, `min_enemies`,
    `max_enemies`, `target_selector`, `movement_directive`,
    `auto_attack_mode`, `max_range`, `min_ready_runes`,
    `requires_ground_target`, `enabled`
)
SELECT
    @blood_profile, 31, 43265, 'aoe',
    'death_and_decay,ground_aoe,pinned_apl,rune_spender,threat',
    1.00, 5.00, 0, 2, 0, 'ground_enemy', 'melee', 'melee', 30.0, 1, 1, 1
WHERE @blood_profile IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM `bot_rotation_action`
      WHERE `profile_id` = @blood_profile
        AND `spell_id` = 43265
  );

UPDATE `bot_rotation_action`
SET `sort_order` = 31,
    `category` = 'aoe',
    `mechanic_tags` = 'death_and_decay,ground_aoe,pinned_apl,rune_spender,threat',
    `damage_weight` = 1.00,
    `threat_weight` = 5.00,
    `priority_bucket` = 0,
    `min_enemies` = 2,
    `max_enemies` = 0,
    `target_selector` = 'ground_enemy',
    `movement_directive` = 'melee',
    `auto_attack_mode` = 'melee',
    `min_range` = 0.0,
    `max_range` = 30.0,
    `min_ready_runes` = 1,
    `requires_ground_target` = 1,
    `enabled` = 1
WHERE `profile_id` = @blood_profile
  AND `spell_id` = 43265;

UPDATE `bot_rotation_action`
SET `priority_bucket` = 0,
    `sort_order` = 32,
    `threat_weight` = 4.00,
    `min_enemies` = GREATEST(`min_enemies`, 2),
    `max_enemies` = 0,
    `enabled` = 1
WHERE `profile_id` = @blood_profile
  AND `spell_id` = 48721;

UPDATE `bot_rotation_action`
SET `priority_bucket` = 1
WHERE `profile_id` = @blood_profile
  AND `spell_id` IN (45462, 45477, 49028, 55050, 56222);

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 20),
    `source_note` = 'phase9_blood_persistent_ground_threat_first_2026_07_29',
    `scope_note` = 'Place Death and Decay before Blood Boil whenever both area-threat actions are ready, then use Blood Boil as the immediate follow-up'
WHERE `id` = @blood_profile;
