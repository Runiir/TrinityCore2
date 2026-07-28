-- Phase 8 Warrior calibration aligns the SQL-authoritative profiles with the
-- Cataclysm Arms and Fury resource/proc rotations.

-- Rend casts 772 but applies periodic aura 94009. Gate refreshes on the aura
-- that is actually present on the target rather than recasting every GCD.
UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`maintain_aura_id` = 94009,
    a.`refresh_aura_below_ms` = 3000,
    a.`forbidden_owned_target_aura` = 0
WHERE p.`class_id` = 1
  AND p.`spec_tag` = 'arms_warrior'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 772;

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`priority_bucket` = 1,
    a.`damage_weight` = 1.05
WHERE p.`class_id` = 1
  AND p.`spec_tag` = 'arms_warrior'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 7384;

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`priority_bucket` = 3,
    a.`damage_weight` = 0.82
WHERE p.`class_id` = 1
  AND p.`spec_tag` = 'arms_warrior'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 1464;

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`priority_bucket` = 3,
    a.`damage_weight` = 0.78
WHERE p.`class_id` = 1
  AND p.`spec_tag` = 'fury_warrior'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 1464;

-- Raging Blow is the Enrage-gated core strike. Keep it behind Colossus
-- Smash and Bloodthirst but ahead of off-GCD Rage dumps and fillers.
UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`priority_bucket` = 1,
    a.`damage_weight` = 0.97
WHERE p.`class_id` = 1
  AND p.`spec_tag` = 'fury_warrior'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 85288;

-- At 20 percent target health, Execute is Fury's primary Rage spender. Put it
-- ahead of the normal core strikes while retaining those actions as Rage
-- generators whenever Execute is unavailable.
UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`priority_bucket` = 0,
    a.`damage_weight` = 1.15
WHERE p.`class_id` = 1
  AND p.`spec_tag` = 'fury_warrior'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 5308;

DELETE a FROM `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
WHERE p.`class_id` = 1
  AND p.`spec_tag` IN ('arms_warrior', 'fury_warrior')
  AND p.`role` = 'dps'
  AND a.`spell_id` IN (78, 1134, 1719, 6673, 85730, 46924, 12292, 18499);

INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
 `damage_weight`, `survival_weight`, `priority_bucket`, `min_enemies`,
 `max_enemies`, `target_selector`, `movement_directive`, `auto_attack_mode`,
 `requires_melee_range`, `min_primary_power_pct`, `maintain_aura_id`,
 `refresh_aura_below_ms`)
VALUES
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 1 AND `spec_tag` = 'arms_warrior' AND `role` = 'dps'),
 45, 78, 'spender', 'heroic_strike,rage_dump,single_target',
 1.02, 0.00, 2, 1, 1, 'enemy', 'melee', 'melee', 1, 0.45, 0, 0),
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 1 AND `spec_tag` = 'arms_warrior' AND `role` = 'dps'),
 5, 1719, 'offensive_cooldown', 'recklessness,self,offensive_cooldown',
 0.95, 0.05, 0, 1, 0, 'self', 'melee', 'melee', 0, 0.00, 1719, 0),
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 1 AND `spec_tag` = 'arms_warrior' AND `role` = 'dps'),
 6, 85730, 'offensive_cooldown', 'deadly_calm,self,offensive_cooldown,rage',
 0.98, 0.00, 0, 1, 0, 'self', 'melee', 'melee', 0, 0.00, 85730, 0),
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 1 AND `spec_tag` = 'arms_warrior' AND `role` = 'dps'),
 7, 46924, 'offensive_cooldown', 'bladestorm,self,offensive_cooldown,aoe',
 1.05, 0.05, 0, 1, 0, 'self', 'melee', 'melee', 0, 0.00, 46924, 0),
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 1 AND `spec_tag` = 'arms_warrior' AND `role` = 'dps'),
 8, 6673, 'resource_generator', 'battle_shout,self,rage_generator,buff',
 0.25, 0.10, 0, 1, 0, 'self', 'melee', 'melee', 0, 0.00, 6673, 3000);

INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
 `damage_weight`, `survival_weight`, `priority_bucket`, `min_enemies`,
 `max_enemies`, `target_selector`, `movement_directive`, `auto_attack_mode`,
 `requires_melee_range`, `min_primary_power_pct`, `maintain_aura_id`,
 `refresh_aura_below_ms`)
VALUES
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 1 AND `spec_tag` = 'fury_warrior' AND `role` = 'dps'),
 4, 1134, 'offensive_cooldown', 'inner_rage,self,offensive_cooldown,rage_dump',
 0.90, 0.00, 0, 1, 0, 'self', 'melee', 'melee', 0, 0.45, 1134, 0),
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 1 AND `spec_tag` = 'fury_warrior' AND `role` = 'dps'),
 45, 78, 'spender', 'heroic_strike,rage_dump,single_target',
 1.02, 0.00, 2, 1, 1, 'enemy', 'melee', 'melee', 1, 0.45, 0, 0),
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 1 AND `spec_tag` = 'fury_warrior' AND `role` = 'dps'),
 5, 1719, 'offensive_cooldown', 'recklessness,self,offensive_cooldown',
 0.95, 0.05, 0, 1, 0, 'self', 'melee', 'melee', 0, 0.00, 1719, 0),
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 1 AND `spec_tag` = 'fury_warrior' AND `role` = 'dps'),
 6, 12292, 'offensive_cooldown', 'death_wish,self,offensive_cooldown,enrage',
 1.00, 0.00, 0, 1, 0, 'self', 'melee', 'melee', 0, 0.00, 12292, 0),
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 1 AND `spec_tag` = 'fury_warrior' AND `role` = 'dps'),
 7, 18499, 'resource_generator', 'berserker_rage,self,enrage,rage_generator',
 0.35, 0.15, 0, 1, 0, 'self', 'melee', 'melee', 0, 0.00, 18499, 0),
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 1 AND `spec_tag` = 'fury_warrior' AND `role` = 'dps'),
 8, 6673, 'resource_generator', 'battle_shout,self,rage_generator,buff',
 0.25, 0.10, 0, 1, 0, 'self', 'melee', 'melee', 0, 0.00, 6673, 3000);

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`forbidden_self_aura` = 46924
WHERE p.`class_id` = 1
  AND p.`spec_tag` = 'arms_warrior'
  AND p.`role` = 'dps'
  AND a.`spell_id` <> 46924;
