-- Phase 8 third role-qualification follow-up. Explicit SQL remains the
-- runtime authority; these rows remove a non-castable tank action and tighten
-- canonical resource priorities for the remaining tank throughput gaps.

-- Protection Warrior: Shockwave's frontal-cone targeting is not represented by
-- the generic enemy-target cast path and starves every other action when the
-- threat pack is active. Cleave is the real multi-target rage dump and preserves
-- the proven Shield Slam/Thunder Clap/Devastate cycle.
DELETE a FROM `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
WHERE p.`class_id` = 1
  AND p.`spec_tag` = 'protection_warrior'
  AND p.`role` = 'tank'
  AND a.`spell_id` IN (845, 46968);

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

-- Protection Paladin: reserve both maintenance and direct Holy Power spenders
-- for a full stack, then prioritize Crusader Strike over filler Judgements.
-- Inquisition wins only when its aura is absent; Shield of the Righteous wins
-- the next full stack while the aura is active.
UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`mechanic_tags` = 'inquisition,holy_power,holy_power_3,maintain_aura',
    a.`damage_weight` = 1.65,
    a.`threat_weight` = 1.55,
    a.`priority_bucket` = 0,
    a.`refresh_aura_below_ms` = 0
WHERE p.`class_id` = 2
  AND p.`spec_tag` = 'protection'
  AND p.`role` = 'tank'
  AND a.`spell_id` = 84963;

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`mechanic_tags` = 'shield_of_the_righteous,holy_power,holy_power_3,threat',
    a.`damage_weight` = 1.50,
    a.`threat_weight` = 1.35,
    a.`priority_bucket` = 0
WHERE p.`class_id` = 2
  AND p.`spec_tag` = 'protection'
  AND p.`role` = 'tank'
  AND a.`spell_id` = 53600;

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`damage_weight` = 1.35,
    a.`threat_weight` = 1.10,
    a.`priority_bucket` = 0
WHERE p.`class_id` = 2
  AND p.`spec_tag` = 'protection'
  AND p.`role` = 'tank'
  AND a.`spell_id` = 35395;

-- Blood Death Knight: hold the first 60 runic power for Dancing Rune Weapon.
-- Rune Strike remains the canonical excess-power dump above that reserve, and
-- the offensive cooldown outranks rune spenders whenever it becomes ready.
UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`damage_weight` = 2.00,
    a.`threat_weight` = 2.00,
    a.`mitigation_weight` = 0.15,
    a.`survival_weight` = 0.10,
    a.`priority_bucket` = 0
WHERE p.`class_id` = 6
  AND p.`spec_tag` = 'blood_death_knight'
  AND p.`role` = 'tank'
  AND a.`spell_id` = 49028;

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`min_primary_power_pct` = 0.65
WHERE p.`class_id` = 6
  AND p.`spec_tag` = 'blood_death_knight'
  AND p.`role` = 'tank'
  AND a.`spell_id` = 56815;

UPDATE `bot_rotation_profile`
SET `version` = `version` + 1,
    `source_note` = 'phase8_role_qualification_tuning3_2026_07_20',
    `scope_note` = 'All-spec Phase 8 deterministic tank resource-priority follow-up'
WHERE (`class_id` = 1 AND `spec_tag` = 'protection_warrior' AND `role` = 'tank')
   OR (`class_id` = 2 AND `spec_tag` = 'protection' AND `role` = 'tank')
   OR (`class_id` = 6 AND `spec_tag` = 'blood_death_knight' AND `role` = 'tank');
