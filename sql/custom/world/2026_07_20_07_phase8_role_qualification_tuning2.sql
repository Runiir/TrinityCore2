-- Phase 8 second role-qualification follow-up. Explicit SQL remains the
-- runtime authority; these rows correct the remaining deterministic tank
-- throughput failures without enabling generic ML decisions.

-- Protection Warrior: Shockwave is a short cone. Require actual melee range so
-- an out-of-range candidate cannot starve the proven Shield Slam/Thunder Clap
-- rotation for an entire tank-threat window.
UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`requires_melee_range` = 1,
    a.`max_range` = 5
WHERE p.`class_id` = 1
  AND p.`spec_tag` = 'protection_warrior'
  AND p.`role` = 'tank'
  AND a.`spell_id` = 46968;

-- Protection Paladin: use the real execute action during the final 20 percent
-- target-health window and promote deterministic fillers between Crusader
-- Strike and Shield of the Righteous cooldowns.
DELETE a FROM `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
WHERE p.`class_id` = 2
  AND p.`spec_tag` = 'protection'
  AND p.`role` = 'tank'
  AND a.`spell_id` = 24275;

INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
 `damage_weight`, `threat_weight`, `priority_bucket`, `min_enemies`,
 `max_enemies`, `max_target_health_pct`, `target_selector`,
 `movement_directive`, `auto_attack_mode`, `max_range`)
VALUES
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 2 AND `spec_tag` = 'protection' AND `role` = 'tank'),
  14, 24275, 'spender', 'hammer_of_wrath,execute,holy_damage,threat',
  1.40, 1.20, 1, 1, 1, 0.20, 'enemy', 'melee', 'melee', 30);

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`damage_weight` = 1.05,
    a.`threat_weight` = 0.80,
    a.`priority_bucket` = 2
WHERE p.`class_id` = 2
  AND p.`spec_tag` = 'protection'
  AND p.`role` = 'tank'
  AND a.`spell_id` = 20271;

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`priority_bucket` = 3
WHERE p.`class_id` = 2
  AND p.`spec_tag` = 'protection'
  AND p.`role` = 'tank'
  AND a.`spell_id` IN (26573, 2812);

-- Blood Death Knight: Rune Strike is the canonical Blood Presence runic-power
-- dump. Heart Strike remains usable against the threat pack so Blood Boil does
-- not monopolize every available blood rune.
DELETE a FROM `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
WHERE p.`class_id` = 6
  AND p.`spec_tag` = 'blood_death_knight'
  AND p.`role` = 'tank'
  AND a.`spell_id` = 56815;

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`damage_weight` = 1.50,
    a.`threat_weight` = 1.50,
    a.`priority_bucket` = 0,
    a.`max_enemies` = 0
WHERE p.`class_id` = 6
  AND p.`spec_tag` = 'blood_death_knight'
  AND p.`role` = 'tank'
  AND a.`spell_id` = 55050;

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`priority_bucket` = 1
WHERE p.`class_id` = 6
  AND p.`spec_tag` = 'blood_death_knight'
  AND p.`role` = 'tank'
  AND a.`spell_id` = 48721;

INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
 `damage_weight`, `threat_weight`, `priority_bucket`, `min_enemies`,
 `max_enemies`, `target_selector`, `movement_directive`, `auto_attack_mode`,
 `requires_melee_range`, `max_range`)
VALUES
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 6 AND `spec_tag` = 'blood_death_knight' AND `role` = 'tank'),
  44, 56815, 'spender', 'rune_strike,runic_power,blood_presence,threat',
  1.45, 1.55, 1, 1, 0, 'enemy', 'melee', 'melee', 1, 5);

-- Feral tank: Thrash is part of the Cataclysm bear single-target bleed cycle,
-- not only an AoE action. The existing real spell supplies the small remaining
-- throughput gap without changing the pinned reference.
UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`min_enemies` = 1,
    a.`mechanic_tags` = 'thrash_bear,bleed,aoe,threat,rotation_primary'
WHERE p.`class_id` = 11
  AND p.`spec_tag` = 'feral_druid_tank'
  AND p.`role` = 'tank'
  AND a.`spell_id` = 77758;

UPDATE `bot_rotation_profile`
SET `version` = `version` + 1,
    `source_note` = 'phase8_role_qualification_tuning2_2026_07_20',
    `scope_note` = 'All-spec Phase 8 deterministic tank throughput follow-up'
WHERE (`class_id` = 1 AND `spec_tag` = 'protection_warrior' AND `role` = 'tank')
   OR (`class_id` = 2 AND `spec_tag` = 'protection' AND `role` = 'tank')
   OR (`class_id` = 6 AND `spec_tag` = 'blood_death_knight' AND `role` = 'tank')
   OR (`class_id` = 11 AND `spec_tag` = 'feral_druid_tank' AND `role` = 'tank');
