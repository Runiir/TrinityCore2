-- Phase 8 Demonology Warlock short-range burst contract.
--
-- The pinned Incinerate APL assumes a close casting lane for Shadowflame and
-- Metamorphosis Immolation Aura. Keep the explicit SQL profile in a stable
-- five-to-eighteen-yard band where the complete ranged rotation remains legal.
-- Keep the pinned Doomguard opener and short-range Shadowflame ahead of filler.

UPDATE `bot_rotation_profile`
SET `movement_directive` = 'ranged',
    `min_range` = 5.0,
    `max_range` = 18.0
WHERE `class_id` = 9
  AND `spec_tag` = 'demonology_warlock'
  AND `role` = 'dps';

UPDATE `bot_rotation_action` AS `action`
INNER JOIN `bot_rotation_profile` AS `profile`
    ON `profile`.`id` = `action`.`profile_id`
SET `action`.`movement_directive` = 'ranged',
    `action`.`max_range` = 18.0
WHERE `profile`.`class_id` = 9
  AND `profile`.`spec_tag` = 'demonology_warlock'
  AND `profile`.`role` = 'dps'
  AND (`action`.`target_selector` = 'enemy' OR `action`.`spell_id` = 50589);

DELETE `action`
FROM `bot_rotation_action` AS `action`
INNER JOIN `bot_rotation_profile` AS `profile`
    ON `profile`.`id` = `action`.`profile_id`
WHERE `profile`.`class_id` = 9
  AND `profile`.`spec_tag` = 'demonology_warlock'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 100612;

UPDATE `bot_rotation_action` AS `action`
INNER JOIN `bot_rotation_profile` AS `profile`
    ON `profile`.`id` = `action`.`profile_id`
SET `action`.`priority_bucket` = 0,
    `action`.`damage_weight` = 1.20
WHERE `profile`.`class_id` = 9
  AND `profile`.`spec_tag` = 'demonology_warlock'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 18540;

UPDATE `bot_rotation_action` AS `action`
INNER JOIN `bot_rotation_profile` AS `profile`
    ON `profile`.`id` = `action`.`profile_id`
SET `action`.`priority_bucket` = 1,
    `action`.`damage_weight` = 1.05,
    `action`.`max_range` = 8.0
WHERE `profile`.`class_id` = 9
  AND `profile`.`spec_tag` = 'demonology_warlock'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 47897;

UPDATE `bot_rotation_action` AS `action`
INNER JOIN `bot_rotation_profile` AS `profile`
    ON `profile`.`id` = `action`.`profile_id`
SET `action`.`max_enemies` = 0
WHERE `profile`.`class_id` = 9
  AND `profile`.`spec_tag` = 'demonology_warlock'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` IN (79476, 33697, 47241, 50589, 77801);

INSERT INTO `bot_rotation_action`
    (`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
     `damage_weight`, `survival_weight`, `priority_bucket`, `min_enemies`,
     `max_enemies`, `min_self_health_pct`, `max_mana_pct`, `target_selector`,
     `movement_directive`, `auto_attack_mode`)
SELECT `profile`.`id`, 65, 1454, 'resource_generator',
       'life_tap,mana_recovery,pinned_apl',
       0.00, 0.25, 0, 1, 0, 0.25, 0.55, 'self', 'hold', 'none'
FROM `bot_rotation_profile` AS `profile`
WHERE `profile`.`class_id` = 9
  AND `profile`.`spec_tag` = 'demonology_warlock'
  AND `profile`.`role` = 'dps'
  AND NOT EXISTS (
      SELECT 1
      FROM `bot_rotation_action` AS `existing`
      WHERE `existing`.`profile_id` = `profile`.`id`
        AND `existing`.`spell_id` = 1454
  );

UPDATE `bot_rotation_action` AS `action`
INNER JOIN `bot_rotation_profile` AS `profile`
    ON `profile`.`id` = `action`.`profile_id`
SET `action`.`min_self_health_pct` = 0.25
WHERE `profile`.`class_id` = 9
  AND `profile`.`spec_tag` = 'demonology_warlock'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 1454;

INSERT INTO `bot_rotation_action`
    (`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
     `damage_weight`, `survival_weight`, `priority_bucket`, `min_enemies`,
     `max_enemies`, `max_self_health_pct`, `target_selector`,
     `movement_directive`, `auto_attack_mode`, `min_range`, `max_range`,
     `requires_ranged_range`)
SELECT `profile`.`id`, 66, 689, 'resource_generator',
       'drain_life,health_recovery,resource_fallback,pinned_apl',
       0.20, 0.80, 0, 1, 0, 0.60, 'enemy', 'ranged', 'none', 5.0, 18.0, 1
FROM `bot_rotation_profile` AS `profile`
WHERE `profile`.`class_id` = 9
  AND `profile`.`spec_tag` = 'demonology_warlock'
  AND `profile`.`role` = 'dps'
  AND NOT EXISTS (
      SELECT 1
      FROM `bot_rotation_action` AS `existing`
      WHERE `existing`.`profile_id` = `profile`.`id`
        AND `existing`.`spell_id` = 689
  );

DELETE `action`
FROM `bot_rotation_action` AS `action`
INNER JOIN `bot_rotation_profile` AS `profile`
    ON `profile`.`id` = `action`.`profile_id`
WHERE `profile`.`class_id` = 9
  AND `profile`.`spec_tag` = 'demonology_warlock'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 29722
  AND `action`.`sort_order` = 76;

INSERT INTO `bot_rotation_action`
    (`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
     `damage_weight`, `survival_weight`, `priority_bucket`, `min_enemies`,
     `max_enemies`, `required_self_aura`, `min_self_aura_remaining_ms`,
     `target_selector`, `movement_directive`, `auto_attack_mode`, `min_range`,
     `max_range`, `requires_ranged_range`)
SELECT `profile`.`id`, 76, 29722, 'builder',
       'incinerate,metamorphosis_aoe_coverage,pinned_apl',
       0.82, 0.00, 0, 3, 0, 47241, 30000, 'enemy', 'ranged', 'none', 5.0, 18.0, 1
FROM `bot_rotation_profile` AS `profile`
WHERE `profile`.`class_id` = 9
  AND `profile`.`spec_tag` = 'demonology_warlock'
  AND `profile`.`role` = 'dps'
  AND NOT EXISTS (
      SELECT 1
      FROM `bot_rotation_action` AS `existing`
      WHERE `existing`.`profile_id` = `profile`.`id`
        AND `existing`.`spell_id` = 29722
        AND `existing`.`required_self_aura` = 47241
  );
