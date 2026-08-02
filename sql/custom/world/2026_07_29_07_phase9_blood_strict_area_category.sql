-- Phase 9 Blood Death Knight strict area-threat classification.
--
-- Rerun31 completed all 14 Stonecore nodes, but Blood retained only 70.38% of
-- identity-scoped hostiles. The strict immediate-area resolver correctly rejected
-- non-area profile actions, yet Blood Boil remained categorized as threat_build
-- despite its explicit aoe mechanic tag. That excluded the repeatable self-centered
-- pickup from strict selection and left only Death and Decay's 30-second window.
-- Classify Blood Boil as authoritative area threat while preserving Death and
-- Decay's higher score, the two-hostile gate, and the existing 2.1 threat trigger.

SET @blood_profile := (
    SELECT `id`
    FROM `bot_rotation_profile`
    WHERE `class_id` = 6
      AND `spec_tag` = 'blood_death_knight'
      AND `role` = 'tank'
    LIMIT 1
);

UPDATE `bot_rotation_action`
SET `category` = 'aoe',
    `mechanic_tags` = 'blood_boil,blood_rune,aoe,threat',
    `priority_bucket` = 0,
    `sort_order` = 32,
    `threat_weight` = GREATEST(`threat_weight`, 4.00),
    `min_enemies` = GREATEST(`min_enemies`, 2),
    `max_enemies` = 0,
    `target_selector` = 'self',
    `movement_directive` = 'melee',
    `auto_attack_mode` = 'melee',
    `min_ready_runes` = GREATEST(`min_ready_runes`, 1),
    `enabled` = 1
WHERE `profile_id` = @blood_profile
  AND `spell_id` = 48721;

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 24),
    `source_note` = 'phase9_blood_strict_area_category_2026_07_29',
    `scope_note` = 'Keep enemy-centered Death and Decay first, then use category-authoritative Blood Boil for repeatable strict area-threat pickup'
WHERE `id` = @blood_profile;
