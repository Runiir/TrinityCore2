-- Phase 8 Demonology Warlock Soulburn burst sequence.
--
-- The pinned Incinerate APL uses Soulburn into Soul Fire and the Orc Blood
-- Fury racial before Demon Soul. Expose those native cooldowns through the
-- explicit profile without changing their server-authored effects or timing.

INSERT INTO `bot_rotation_action`
    (`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
     `damage_weight`, `survival_weight`, `priority_bucket`, `min_enemies`,
     `max_enemies`, `target_selector`, `movement_directive`,
     `auto_attack_mode`, `maintain_aura_id`, `forbidden_self_aura`)
SELECT `profile`.`id`, 17, 74434, 'offensive_cooldown',
       'soulburn,soul_fire_setup,pinned_apl',
       1.05, 0.00, 1, 1, 1, 'self', 'hold', 'none', 74434, 74434
FROM `bot_rotation_profile` AS `profile`
WHERE `profile`.`class_id` = 9
  AND `profile`.`spec_tag` = 'demonology_warlock'
  AND `profile`.`role` = 'dps'
  AND NOT EXISTS (
      SELECT 1
      FROM `bot_rotation_action` AS `existing`
      WHERE `existing`.`profile_id` = `profile`.`id`
        AND `existing`.`spell_id` = 74434
  );

INSERT INTO `bot_rotation_action`
    (`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
     `damage_weight`, `survival_weight`, `priority_bucket`, `min_enemies`,
     `max_enemies`, `target_selector`, `movement_directive`,
     `auto_attack_mode`, `min_range`, `max_range`,
     `requires_ranged_range`, `required_self_aura`)
SELECT `profile`.`id`, 18, 6353, 'offensive_cooldown',
       'soul_fire,soulburn_consumer,improved_soul_fire,pinned_apl',
       1.10, 0.00, 1, 1, 1, 'enemy', 'ranged', 'none', 5, 35, 1, 74434
FROM `bot_rotation_profile` AS `profile`
WHERE `profile`.`class_id` = 9
  AND `profile`.`spec_tag` = 'demonology_warlock'
  AND `profile`.`role` = 'dps'
  AND NOT EXISTS (
      SELECT 1
      FROM `bot_rotation_action` AS `existing`
      WHERE `existing`.`profile_id` = `profile`.`id`
        AND `existing`.`spell_id` = 6353
        AND `existing`.`required_self_aura` = 74434
  );

INSERT INTO `bot_rotation_action`
    (`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
     `damage_weight`, `survival_weight`, `priority_bucket`, `min_enemies`,
     `max_enemies`, `target_selector`, `movement_directive`,
     `auto_attack_mode`, `maintain_aura_id`)
SELECT `profile`.`id`, 8, 33697, 'offensive_cooldown',
       'blood_fury,racial,spell_power,pinned_apl',
       1.05, 0.00, 1, 1, 1, 'self', 'hold', 'none', 33697
FROM `bot_rotation_profile` AS `profile`
WHERE `profile`.`class_id` = 9
  AND `profile`.`spec_tag` = 'demonology_warlock'
  AND `profile`.`role` = 'dps'
  AND NOT EXISTS (
      SELECT 1
      FROM `bot_rotation_action` AS `existing`
      WHERE `existing`.`profile_id` = `profile`.`id`
        AND `existing`.`spell_id` = 33697
  );

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`sort_order` = 8,
    `action`.`forbidden_self_aura` = 47241
WHERE `profile`.`class_id` = 9
  AND `profile`.`spec_tag` = 'demonology_warlock'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 33697;
