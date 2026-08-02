-- Phase 9 Blood Death Knight self-centered persistent area threat.
--
-- The enemy-centered Death and Decay in rerun15 did not cover the tank/healer
-- pickup stack consistently: Azil's second and third full follower waves retained
-- 37/77 and 84/130 eligible samples despite immediate Blood Boil and tighter
-- healer positioning. Place the ground field under the tank so followers and
-- ordinary melee trash converge through persistent threat rather than leaving the
-- field behind on a moving cluster representative.

SET @blood_profile := (
    SELECT `id`
    FROM `bot_rotation_profile`
    WHERE `class_id` = 6
      AND `spec_tag` = 'blood_death_knight'
      AND `role` = 'tank'
    LIMIT 1
);

UPDATE `bot_rotation_action`
SET `target_selector` = 'self'
WHERE `profile_id` = @blood_profile
  AND `spell_id` = 43265;

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 21),
    `source_note` = 'phase9_blood_self_centered_ground_threat_2026_07_29',
    `scope_note` = 'Place Death and Decay under the tank before immediate Blood Boil so persistent area threat covers the melee pickup stack'
WHERE `id` = @blood_profile;
