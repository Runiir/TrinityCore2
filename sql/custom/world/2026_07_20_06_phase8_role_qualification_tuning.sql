-- Phase 8 role-qualification follow-up from the first complete tank/healer
-- seed. Explicit SQL remains the runtime authority; these rows add missing
-- Cataclysm response, threat, and resource-priority actions without enabling
-- the generic ML policy for live decisions.

-- Protection Warrior: Shockwave supplies a second deterministic multi-target
-- threat refresh between Thunder Clap windows.
DELETE a FROM `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
WHERE p.`class_id` = 1 AND p.`spec_tag` = 'protection_warrior' AND p.`role` = 'tank'
  AND a.`spell_id` = 46968;

INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
 `damage_weight`, `threat_weight`, `priority_bucket`, `min_enemies`,
 `target_selector`, `movement_directive`, `auto_attack_mode`, `max_range`)
VALUES
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 1 AND `spec_tag` = 'protection_warrior' AND `role` = 'tank'),
 47, 46968, 'threat_build', 'shockwave,aoe,threat,rotation_primary',
 1.10, 1.35, 1, 2, 'enemy', 'melee', 'melee', 10);

-- Protection Paladin: Inquisition is also the single-target Holy-damage
-- maintenance spender. Require a full Holy Power stack and refresh only near
-- expiry so Shield of the Righteous remains the normal direct spender.
UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`mechanic_tags` = 'inquisition,holy_power,holy_power_3,maintain_aura',
    a.`damage_weight` = 1.15,
    a.`threat_weight` = 1.10,
    a.`priority_bucket` = 0,
    a.`min_enemies` = 1,
    a.`maintain_aura_id` = 84963,
    a.`refresh_aura_below_ms` = 3000
WHERE p.`class_id` = 2 AND p.`spec_tag` = 'protection' AND p.`role` = 'tank'
  AND a.`spell_id` = 84963;

-- Blood Death Knight: establish both diseases before rune spenders, use Heart
-- Strike on one target, and use Blood Boil to refresh real damage/threat across
-- the tank-threat dummy pack. Dancing Rune Weapon is the real offensive threat
-- cooldown for both branches.
DELETE a FROM `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
WHERE p.`class_id` = 6 AND p.`spec_tag` = 'blood_death_knight' AND p.`role` = 'tank'
  AND a.`spell_id` IN (48721, 49028, 55050);

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`priority_bucket` = 0,
    a.`damage_weight` = 1.05,
    a.`threat_weight` = 1.20,
    a.`maintain_aura_id` = 55095,
    a.`refresh_aura_below_ms` = 3000
WHERE p.`class_id` = 6 AND p.`spec_tag` = 'blood_death_knight' AND p.`role` = 'tank'
  AND a.`spell_id` = 45477;

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`priority_bucket` = 0,
    a.`damage_weight` = 1.05,
    a.`threat_weight` = 1.15,
    a.`maintain_aura_id` = 55078,
    a.`refresh_aura_below_ms` = 3000
WHERE p.`class_id` = 6 AND p.`spec_tag` = 'blood_death_knight' AND p.`role` = 'tank'
  AND a.`spell_id` = 45462;

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`priority_bucket` = 2
WHERE p.`class_id` = 6 AND p.`spec_tag` = 'blood_death_knight' AND p.`role` = 'tank'
  AND a.`spell_id` = 49998;

INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
 `damage_weight`, `threat_weight`, `mitigation_weight`, `survival_weight`,
 `priority_bucket`, `min_enemies`, `max_enemies`, `target_selector`,
 `movement_directive`, `auto_attack_mode`, `requires_melee_range`,
 `min_ready_runes`)
VALUES
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 6 AND `spec_tag` = 'blood_death_knight' AND `role` = 'tank'),
 42, 55050, 'builder', 'heart_strike,blood_rune,single_target,threat',
 1.30, 1.25, 0.00, 0.00, 1, 1, 1, 'enemy', 'melee', 'melee', 1, 1),
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 6 AND `spec_tag` = 'blood_death_knight' AND `role` = 'tank'),
 43, 48721, 'threat_build', 'blood_boil,blood_rune,aoe,threat',
 1.20, 1.45, 0.00, 0.00, 0, 2, 0, 'self', 'melee', 'melee', 0, 1),
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 6 AND `spec_tag` = 'blood_death_knight' AND `role` = 'tank'),
 15, 49028, 'offensive_cooldown', 'dancing_rune_weapon,offensive_cooldown,threat',
 1.35, 1.40, 0.15, 0.10, 0, 1, 0, 'enemy', 'melee', 'melee', 0, 0);

-- Discipline Priest: Power Word: Shield is the deterministic instant response
-- action. Weakened Soul remains the native recast guard.
DELETE a FROM `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
WHERE p.`class_id` = 5 AND p.`spec_tag` = 'discipline_priest' AND p.`role` = 'healer'
  AND a.`spell_id` = 17;

INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
 `healing_weight`, `survival_weight`, `priority_bucket`, `max_target_health_pct`,
 `forbidden_target_aura`, `target_selector`, `movement_directive`,
 `auto_attack_mode`, `max_range`, `maintain_aura_id`, `min_injured_players`,
 `injured_health_pct`)
VALUES
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 5 AND `spec_tag` = 'discipline_priest' AND `role` = 'healer'),
 5, 17, 'heal_fast', 'power_word_shield,absorb,instant,triage',
 1.35, 1.00, 0, 0.94, 6788, 'lowest_ally', 'healer_support', 'none',
 40, 17, 1, 0.94);

-- Holy Priest: Renew is the stable instant response while Serenity remains
-- correctly gated behind Chakra: Serenity and cast-time heals retain emergency
-- throughput.
UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`healing_weight` = 1.35,
    a.`survival_weight` = 0.70,
    a.`priority_bucket` = 0,
    a.`max_target_health_pct` = 0.94,
    a.`target_selector` = 'lowest_ally',
    a.`maintain_aura_id` = 139,
    a.`refresh_aura_below_ms` = 3000,
    a.`mechanic_tags` = 'renew,hot,instant,triage,maintain_aura'
WHERE p.`class_id` = 5 AND p.`spec_tag` = 'holy_priest' AND p.`role` = 'healer'
  AND a.`spell_id` = 139;

-- Restoration Druid: Rejuvenation provides the missing instant response,
-- Swiftmend consumes that real HoT for burst triage, and Wild Growth handles
-- deterministic group-damage periods.
DELETE a FROM `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
WHERE p.`class_id` = 11 AND p.`spec_tag` = 'restoration_druid' AND p.`role` = 'healer'
  AND a.`spell_id` IN (774, 18562, 48438);

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`healing_weight` = CASE
      WHEN a.`spell_id` = 8936 THEN 0.95
      WHEN a.`spell_id` = 5185 THEN 0.85
      ELSE a.`healing_weight` END,
    a.`priority_bucket` = CASE
      WHEN a.`spell_id` = 8936 THEN 2
      WHEN a.`spell_id` = 5185 THEN 3
      ELSE a.`priority_bucket` END
WHERE p.`class_id` = 11 AND p.`spec_tag` = 'restoration_druid' AND p.`role` = 'healer'
  AND a.`spell_id` IN (8936, 5185);

INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
 `healing_weight`, `survival_weight`, `priority_bucket`, `max_target_health_pct`,
 `required_target_aura`, `target_selector`, `movement_directive`,
 `auto_attack_mode`, `max_range`, `maintain_aura_id`, `refresh_aura_below_ms`,
 `min_injured_players`, `injured_health_pct`)
VALUES
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 11 AND `spec_tag` = 'restoration_druid' AND `role` = 'healer'),
 5, 774, 'heal_fast', 'rejuvenation,hot,instant,triage,maintain_aura',
 1.40, 0.70, 0, 0.94, 0, 'lowest_ally', 'healer_support', 'none',
 40, 774, 3000, 1, 0.94),
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 11 AND `spec_tag` = 'restoration_druid' AND `role` = 'healer'),
 6, 18562, 'heal_fast', 'swiftmend,instant,triage,requires_rejuvenation',
 1.55, 0.85, 0, 0.70, 774, 'lowest_ally', 'healer_support', 'none',
 40, 0, 0, 1, 0.70),
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 11 AND `spec_tag` = 'restoration_druid' AND `role` = 'healer'),
 7, 48438, 'heal_aoe', 'wild_growth,hot,instant,group_heal',
 1.30, 0.70, 1, 0.90, 0, 'lowest_ally', 'healer_support', 'none',
 40, 0, 0, 3, 0.90);

UPDATE `bot_rotation_profile`
SET `version` = `version` + 1,
    `source_note` = 'phase8_role_qualification_tuning_2026_07_20',
    `scope_note` = 'All-spec Phase 8 deterministic tank and healer qualification follow-up'
WHERE (`class_id` = 1 AND `spec_tag` = 'protection_warrior' AND `role` = 'tank')
   OR (`class_id` = 2 AND `spec_tag` = 'protection' AND `role` = 'tank')
   OR (`class_id` = 6 AND `spec_tag` = 'blood_death_knight' AND `role` = 'tank')
   OR (`class_id` = 5 AND `spec_tag` IN ('discipline_priest', 'holy_priest') AND `role` = 'healer')
   OR (`class_id` = 11 AND `spec_tag` = 'restoration_druid' AND `role` = 'healer');
