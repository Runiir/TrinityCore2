-- Stonecore 5N role-efficiency corrections from run 077.
ALTER TABLE `bot_rotation_action`
  ADD COLUMN IF NOT EXISTS `required_self_aura_stacks` TINYINT UNSIGNED NOT NULL DEFAULT 0 AFTER `requires_moving`;

UPDATE `bot_rotation_profile`
SET `version` = 2, `scope_note` = 'Stonecore 5N role-efficient threat, triage, and sustained damage profile'
WHERE (`class_id` = 2 AND `spec_tag` = 'protection' AND `role` = 'tank')
   OR (`class_id` = 5 AND `spec_tag` = 'holy_priest' AND `role` = 'healer')
   OR (`class_id` = 8 AND `spec_tag` = 'fire' AND `role` = 'dps')
   OR (`class_id` = 3 AND `spec_tag` = 'marksmanship' AND `role` = 'dps')
   OR (`class_id` = 7 AND `spec_tag` = 'enhancement' AND `role` = 'dps');

-- Keep earlier liveness corrections in this idempotent migration as well.
-- The DB updater may legitimately replay the destructive seed migration when
-- its schema changes, after the older correction file is already archived.
UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`target_selector` = 'self'
WHERE p.`class_id` = 2 AND p.`spec_tag` = 'protection' AND p.`role` = 'tank'
  AND a.`spell_id` = 498;

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`damage_weight` = 0.55, a.`min_enemies` = 5
WHERE p.`class_id` = 8 AND p.`spec_tag` = 'fire' AND p.`role` = 'dps'
  AND a.`spell_id` = 2120;

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`required_target_aura` = 1978
WHERE p.`class_id` = 3 AND p.`spec_tag` = 'marksmanship' AND p.`role` = 'dps'
  AND a.`spell_id` = 53209;

-- Consecration is placed under the paladin, not under its hostile target.
UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`target_selector` = 'self'
WHERE p.`class_id` = 2 AND p.`spec_tag` = 'protection' AND p.`role` = 'tank'
  AND a.`spell_id` = 26573;

-- Cataclysm ranged attacks retain a dead zone beyond the nominal five-yard
-- spell minimum once combat reach is included. Hold ten yards so the actor
-- moves before submitting shots that the server will reject as TOO_CLOSE.
UPDATE `bot_rotation_profile`
SET `min_range` = 10
WHERE `class_id` = 3 AND `spec_tag` = 'marksmanship' AND `role` = 'dps';

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`min_range` = 10
WHERE p.`class_id` = 3 AND p.`spec_tag` = 'marksmanship' AND p.`role` = 'dps'
  AND a.`target_selector` = 'enemy' AND a.`min_range` > 0;

-- Never hard-cast enhancement Lightning Bolt/Chain Lightning below five
-- Maelstrom Weapon stacks; doing so destroys melee and white-swing uptime.
UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`required_self_aura_stacks` = 5
WHERE p.`class_id` = 7 AND p.`spec_tag` = 'enhancement' AND p.`role` = 'dps'
  AND a.`spell_id` IN (403, 421);

-- Interrupts are now runtime-gated on a real cast, so they can safely outrank
-- rotational damage without being proposed every decision tick.
UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`priority_bucket` = 0
WHERE ((p.`class_id` = 2 AND p.`spec_tag` = 'protection' AND p.`role` = 'tank' AND a.`spell_id` = 96231)
    OR (p.`class_id` = 8 AND p.`spec_tag` = 'fire' AND p.`role` = 'dps' AND a.`spell_id` = 2139)
    OR (p.`class_id` = 7 AND p.`spec_tag` = 'enhancement' AND p.`role` = 'dps' AND a.`spell_id` = 57994));

-- Keep this migration idempotent when validation provisioning replays custom SQL.
DELETE a FROM `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
WHERE (p.`class_id` = 2 AND p.`spec_tag` = 'protection' AND p.`role` = 'tank' AND a.`spell_id` IN (31850, 85673, 86150))
   OR (p.`class_id` = 8 AND p.`spec_tag` = 'fire' AND p.`role` = 'dps' AND a.`spell_id` = 11129)
   OR (p.`class_id` = 3 AND p.`spec_tag` = 'marksmanship' AND p.`role` = 'dps' AND a.`spell_id` IN (3045, 34490))
   OR (p.`class_id` = 7 AND p.`spec_tag` = 'enhancement' AND p.`role` = 'dps' AND a.`spell_id` IN (30823, 51533, 73680));

INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`, `damage_weight`, `healing_weight`, `threat_weight`, `mitigation_weight`, `survival_weight`, `priority_bucket`, `max_self_health_pct`, `required_target_aura`, `target_selector`, `movement_directive`, `auto_attack_mode`)
VALUES
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=2 AND `spec_tag`='protection' AND `role`='tank'), 25, 31850, 'defensive', 'ardent_defender,emergency,tank', 0, 0, 0.10, 1.00, 1.00, 0, 0.35, 0, 'self', 'melee', 'melee'),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=2 AND `spec_tag`='protection' AND `role`='tank'), 26, 85673, 'defensive', 'word_of_glory,self_heal,tank', 0, 1.00, 0.10, 0.40, 1.00, 0, 0.45, 0, 'self', 'melee', 'melee'),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=2 AND `spec_tag`='protection' AND `role`='tank'), 27, 86150, 'defensive', 'guardian_of_ancient_kings,major_defensive,tank', 0, 0, 0.10, 1.00, 1.00, 1, 0.55, 0, 'self', 'melee', 'melee'),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=8 AND `spec_tag`='fire' AND `role`='dps'), 35, 11129, 'offensive_cooldown', 'combustion,burn', 1.00, 0, 0, 0, 0, 2, 1.00, 44457, 'enemy', 'ranged', 'none'),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=3 AND `spec_tag`='marksmanship' AND `role`='dps'), 15, 3045, 'offensive_cooldown', 'rapid_fire,burn', 1.20, 0, 0, 0, 0, 1, 1.00, 0, 'self', 'ranged', 'ranged'),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=3 AND `spec_tag`='marksmanship' AND `role`='dps'), 16, 34490, 'interrupt', 'silencing_shot,interrupt', 0.20, 0, 0, 0, 0.20, 0, 1.00, 0, 'enemy', 'ranged', 'ranged'),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=7 AND `spec_tag`='enhancement' AND `role`='dps'), 15, 30823, 'defensive', 'shamanistic_rage,defensive,mana', 0, 0, 0, 0.80, 0.90, 0, 0.55, 0, 'self', 'melee', 'melee'),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=7 AND `spec_tag`='enhancement' AND `role`='dps'), 35, 51533, 'offensive_cooldown', 'feral_spirit,burn', 0.98, 0, 0, 0, 0.30, 2, 1.00, 0, 'self', 'melee', 'melee'),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=7 AND `spec_tag`='enhancement' AND `role`='dps'), 45, 73680, 'spender', 'unleash_elements,melee', 0.94, 0, 0, 0, 0, 2, 1.00, 0, 'enemy', 'melee', 'melee');

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`requires_interruptible_target` = 1
WHERE p.`class_id` = 3 AND p.`spec_tag` = 'marksmanship' AND p.`role` = 'dps'
  AND a.`spell_id` = 34490;
