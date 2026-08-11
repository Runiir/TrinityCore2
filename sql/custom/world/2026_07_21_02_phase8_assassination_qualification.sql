-- Phase 8 Assassination qualification replaces the legacy four-action
-- Sinister Strike/Eviscerate profile with the pinned Cataclysm priority.
-- Weapon poisons are provisioned as temporary enchants by the exact gear overlay;
-- the rotation remains usable without enchant predicates for clean diagnostics.

DELETE a FROM `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
WHERE p.`class_id` = 4
  AND p.`spec_tag` = 'assassination_rogue'
  AND p.`role` = 'dps';

INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
 `damage_weight`, `survival_weight`, `priority_bucket`, `min_enemies`, `max_enemies`,
 `max_target_health_pct`, `requires_interruptible_target`, `requires_melee_range`,
 `target_selector`, `movement_directive`, `auto_attack_mode`, `min_range`, `max_range`,
 `maintain_aura_id`, `min_primary_power_pct`, `forbidden_self_aura`,
 `forbidden_owned_target_aura`, `min_combo_points`, `max_combo_points`, `cooldown_group`)
VALUES
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 4 AND `spec_tag` = 'assassination_rogue' AND `role` = 'dps'),
 10, 1766, 'interrupt', 'kick,interrupt',
 0.15, 0.20, 0, 1, 1, 1.00, 1, 1,
 'enemy', 'melee', 'melee', 0, 5, 0, 0.00, 0, 0, 0, 0, ''),
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 4 AND `spec_tag` = 'assassination_rogue' AND `role` = 'dps'),
 20, 79140, 'offensive_cooldown', 'vendetta,target,burst',
 1.05, 0.10, 1, 1, 1, 1.00, 0, 1,
 'enemy', 'melee', 'melee', 0, 5, 0, 0.00, 0, 0, 0, 0, 'vendetta'),
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 4 AND `spec_tag` = 'assassination_rogue' AND `role` = 'dps'),
 30, 14177, 'offensive_cooldown', 'cold_blood,self,next_finisher',
 0.90, 0.10, 1, 1, 1, 1.00, 0, 0,
 'self', 'melee', 'melee', 0, 0, 0, 0.00, 0, 0, 0, 0, 'cold_blood'),
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 4 AND `spec_tag` = 'assassination_rogue' AND `role` = 'dps'),
 40, 5171, 'buff', 'slice_and_dice,self,haste,initial_finisher',
 0.88, 0.20, 2, 1, 1, 1.00, 0, 0,
 'self', 'melee', 'melee', 0, 0, 5171, 0.00, 5171, 0, 1, 0, ''),
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 4 AND `spec_tag` = 'assassination_rogue' AND `role` = 'dps'),
 50, 1943, 'dot', 'rupture,owned_bleed,venomous_wounds',
 0.98, 0.00, 3, 1, 1, 1.00, 0, 1,
 'enemy', 'melee', 'melee', 0, 5, 1943, 0.00, 0, 1943, 4, 0, ''),
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 4 AND `spec_tag` = 'assassination_rogue' AND `role` = 'dps'),
 60, 53, 'builder', 'backstab,execute,combo_builder',
 1.00, 0.00, 4, 1, 1, 0.35, 0, 1,
 'enemy', 'melee', 'melee', 0, 5, 0, 0.00, 0, 0, 0, 4, ''),
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 4 AND `spec_tag` = 'assassination_rogue' AND `role` = 'dps'),
 70, 32645, 'spender', 'envenom,primary_finisher,cut_to_the_chase',
 1.10, 0.00, 4, 1, 1, 1.00, 0, 1,
 'enemy', 'melee', 'melee', 0, 5, 0, 0.00, 0, 0, 4, 0, ''),
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 4 AND `spec_tag` = 'assassination_rogue' AND `role` = 'dps'),
 80, 1329, 'builder', 'mutilate,primary_builder,combo_builder',
 1.00, 0.00, 5, 1, 1, 1.00, 0, 1,
 'enemy', 'melee', 'melee', 0, 5, 0, 0.00, 0, 0, 0, 3, ''),
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 4 AND `spec_tag` = 'assassination_rogue' AND `role` = 'dps'),
 90, 51723, 'aoe', 'fan_of_knives,aoe,poison_application',
 0.92, 0.00, 2, 2, 0, 1.00, 0, 0,
 'enemy', 'melee', 'melee', 0, 10, 0, 0.00, 0, 0, 0, 0, '');

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 7),
    `source_note` = 'phase8_assassination_qualification_2026_07_21',
    `scope_note` = 'Mutilate, Slice and Dice, Rupture, Envenom, execute Backstab, cooldowns, and Fan of Knives'
WHERE `class_id` = 4
  AND `spec_tag` = 'assassination_rogue'
  AND `role` = 'dps';
