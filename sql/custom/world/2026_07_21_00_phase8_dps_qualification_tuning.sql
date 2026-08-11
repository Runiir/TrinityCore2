-- Phase 8 DPS qualification fixes persistent Hunter setup actions and adds
-- deterministic Warrior multi-target Rage spenders.

-- Persistent setup owns pet recovery. Combat selection may summon only when no
-- Pet object exists, and must not repeatedly cast Revive Pet during the scored
-- window. Aspect of the Hawk is maintained by aura state.
UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`maintain_aura_id` = 13165,
    a.`refresh_aura_below_ms` = 0
WHERE p.`class_id` = 3
  AND p.`spec_tag` = 'marksmanship'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 13165;

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`forbids_pet` = 1
WHERE p.`class_id` = 3
  AND p.`spec_tag` IN ('marksmanship', 'survival')
  AND p.`role` = 'dps'
  AND a.`spell_id` = 883;

DELETE a FROM `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
WHERE p.`class_id` = 3
  AND p.`spec_tag` IN ('marksmanship', 'survival')
  AND p.`role` = 'dps'
  AND a.`spell_id` = 982;

-- Arms Whirlwind is Berserker-Stance-only in Cataclysm. Keep the profile in
-- Battle Stance and use its legal AoE kit: Bladestorm, Sweeping Strikes,
-- Thunder Clap, and Cleave. Fury retains Whirlwind and gains Cleave as its
-- high-Rage multi-target dump.
DELETE a FROM `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
WHERE p.`class_id` = 1
  AND p.`spec_tag` IN ('arms_warrior', 'fury_warrior')
  AND p.`role` = 'dps'
  AND a.`spell_id` = 845;

DELETE a FROM `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
WHERE p.`class_id` = 1
  AND p.`spec_tag` = 'arms_warrior'
  AND p.`role` = 'dps'
  AND a.`spell_id` IN (1680, 12328, 6343);

INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
 `damage_weight`, `priority_bucket`, `min_enemies`, `max_enemies`,
 `target_selector`, `movement_directive`, `auto_attack_mode`,
 `requires_melee_range`, `min_primary_power_pct`, `maintain_aura_id`,
 `refresh_aura_below_ms`, `forbidden_self_aura`)
VALUES
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 1 AND `spec_tag` = 'arms_warrior' AND `role` = 'dps'),
 8, 12328, 'offensive_cooldown', 'sweeping_strikes,self,offensive_cooldown,aoe',
 1.02, 0, 2, 0, 'self', 'melee', 'melee', 0, 0.00, 12328, 0, 46924),
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 1 AND `spec_tag` = 'arms_warrior' AND `role` = 'dps'),
 55, 6343, 'aoe', 'thunder_clap,aoe,rage_spender',
 0.95, 1, 2, 0, 'enemy', 'melee', 'melee', 1, 0.20, 0, 0, 46924),
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 1 AND `spec_tag` = 'arms_warrior' AND `role` = 'dps'),
 56, 845, 'cleave', 'cleave,aoe,rage_dump',
 1.00, 2, 2, 0, 'enemy', 'melee', 'melee', 1, 0.45, 0, 0, 46924),
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 1 AND `spec_tag` = 'fury_warrior' AND `role` = 'dps'),
 56, 845, 'cleave', 'cleave,aoe,rage_dump',
 1.00, 2, 2, 0, 'enemy', 'melee', 'melee', 1, 0.45, 0, 0, 0);

-- Restore the last legal Fury single-target resource gates. The 30-Rage
-- Heroic Strike threshold overspent Rage, while requiring every Slam to be
-- instant removed Slam entirely because the profile has no Bloodsurge gate.
UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`min_primary_power_pct` = 0.45
WHERE p.`class_id` = 1
  AND p.`spec_tag` = 'fury_warrior'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 78;

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`requires_instant_cast` = 0
WHERE p.`class_id` = 1
  AND p.`spec_tag` = 'fury_warrior'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 1464;

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 5),
    `source_note` = 'phase8_dps_qualification_tuning_2026_07_21',
    `scope_note` = 'state-gated Hunter setup and deterministic Warrior single-target/AoE qualification'
WHERE (`class_id` = 3 AND `spec_tag` IN ('marksmanship', 'survival') AND `role` = 'dps')
   OR (`class_id` = 1 AND `spec_tag` IN ('arms_warrior', 'fury_warrior') AND `role` = 'dps');
