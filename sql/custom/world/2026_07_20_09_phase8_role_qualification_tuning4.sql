-- Phase 8 fourth role-qualification follow-up. Explicit SQL remains the
-- runtime authority; these rows correct verified spell-rank and dispel
-- mismatches and revert resource gates that reduced tank throughput.

-- Protection Warrior: Cataclysm uses the rankless Cleave spell. Promote
-- Thunder Clap as the opener so all three threat dummies receive recent damage
-- before the deterministic ten-second snap-threat check while retaining its
-- proven single-target contribution.
DELETE a FROM `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
WHERE p.`class_id` = 1
  AND p.`spec_tag` = 'protection_warrior'
  AND p.`role` = 'tank'
  AND a.`spell_id` IN (845, 47520);

INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
 `damage_weight`, `threat_weight`, `priority_bucket`, `min_enemies`,
 `target_selector`, `movement_directive`, `auto_attack_mode`,
 `requires_melee_range`, `min_primary_power_pct`, `max_range`)
VALUES
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 1 AND `spec_tag` = 'protection_warrior' AND `role` = 'tank'),
  47, 845, 'cleave', 'cleave,aoe,rage_dump,threat,rotation_primary',
  1.00, 1.40, 1, 2, 'enemy', 'melee', 'melee', 1, 0.25, 5);

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`damage_weight` = 1.10,
    a.`threat_weight` = 1.60,
    a.`priority_bucket` = 1,
    a.`min_enemies` = 1,
    a.`mechanic_tags` = 'thunder_clap,aoe,threat,rotation_primary,snap_threat'
WHERE p.`class_id` = 1
  AND p.`spec_tag` = 'protection_warrior'
  AND p.`role` = 'tank'
  AND a.`spell_id` = 6343;

-- Protection Paladin: restore the last higher-throughput Holy Power ordering.
-- Holy Wrath damages every nearby enemy in Cataclysm; creature type limits only
-- its stun, so the whole-action undead/demon gate incorrectly removed a real
-- single-target filler.
UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`mechanic_tags` = 'inquisition,holy_power,holy_power_3,maintain_aura',
    a.`damage_weight` = 1.15,
    a.`threat_weight` = 1.10,
    a.`priority_bucket` = 0,
    a.`refresh_aura_below_ms` = 3000
WHERE p.`class_id` = 2
  AND p.`spec_tag` = 'protection'
  AND p.`role` = 'tank'
  AND a.`spell_id` = 84963;

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`mechanic_tags` = 'shield_of_the_righteous,holy_power,threat',
    a.`damage_weight` = 0.86,
    a.`threat_weight` = 1.00,
    a.`priority_bucket` = 2
WHERE p.`class_id` = 2
  AND p.`spec_tag` = 'protection'
  AND p.`role` = 'tank'
  AND a.`spell_id` = 53600;

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`damage_weight` = 0.76,
    a.`threat_weight` = 0.65,
    a.`priority_bucket` = 3
WHERE p.`class_id` = 2
  AND p.`spec_tag` = 'protection'
  AND p.`role` = 'tank'
  AND a.`spell_id` = 35395;

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`mechanic_tags` = 'holy_wrath,holy_damage,aoe_threat,single_target_filler',
    a.`min_enemies` = 1,
    a.`priority_bucket` = 3,
    a.`target_creature_type_mask` = 0
WHERE p.`class_id` = 2
  AND p.`spec_tag` = 'protection'
  AND p.`role` = 'tank'
  AND a.`spell_id` = 2812;

-- Blood Death Knight: Dancing Rune Weapon keeps its proven cooldown priority,
-- but Rune Strike must consume ordinary runic power instead of being disabled
-- behind a 65-percent reserve for the entire scored window.
UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`min_primary_power_pct` = 0.00
WHERE p.`class_id` = 6
  AND p.`spec_tag` = 'blood_death_knight'
  AND p.`role` = 'tank'
  AND a.`spell_id` = 56815;

-- Restoration Druid: Remove Corruption is the active Cataclysm curse/poison
-- cleanse. Nature's Cure is the talent upgrade and did not remove either
-- controlled aura in live qualification.
DELETE a FROM `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
WHERE p.`class_id` = 11
  AND p.`spec_tag` = 'restoration_druid'
  AND p.`role` = 'healer'
  AND a.`spell_id` IN (2782, 88423);

INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
 `healing_weight`, `survival_weight`, `priority_bucket`,
 `min_injured_players`, `injured_health_pct`, `target_selector`,
 `movement_directive`, `auto_attack_mode`, `max_range`, `maintain_aura_id`)
VALUES
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 11 AND `spec_tag` = 'restoration_druid' AND `role` = 'healer'),
  50, 2782, 'dispel_cleanse', 'remove_corruption,curse,poison,dispel',
  0.20, 0.65, 1, 1, 1.00, 'lowest_ally', 'healer_support', 'none', 40, 0);

UPDATE `bot_rotation_profile`
SET `version` = `version` + 1,
    `source_note` = 'phase8_role_qualification_tuning4_2026_07_20',
    `scope_note` = 'All-spec Phase 8 verified spell-rank, filler, resource, and dispel correction'
WHERE (`class_id` = 1 AND `spec_tag` = 'protection_warrior' AND `role` = 'tank')
   OR (`class_id` = 2 AND `spec_tag` = 'protection' AND `role` = 'tank')
   OR (`class_id` = 6 AND `spec_tag` = 'blood_death_knight' AND `role` = 'tank')
   OR (`class_id` = 11 AND `spec_tag` = 'restoration_druid' AND `role` = 'healer');
