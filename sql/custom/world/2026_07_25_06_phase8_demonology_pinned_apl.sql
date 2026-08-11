-- Phase 8 Demonology Warlock pinned-APL damage recovery.
--
-- The live Felguard/ranged-lane proof produced a legal, failure-free rotation,
-- but reached only 54.35% of the pinned reference because the original profile
-- omitted Bane of Doom, Shadowflame, Immolation Aura, and the preset's Incinerate
-- filler. Restore those authoritative APL actions and retire the Shadow Bolt
-- fallback that belongs to a different Demonology preset.

INSERT INTO `bot_rotation_action`
    (`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
     `damage_weight`, `survival_weight`, `priority_bucket`, `min_enemies`,
     `max_enemies`, `target_selector`, `movement_directive`, `auto_attack_mode`,
     `min_range`, `max_range`, `maintain_aura_id`, `required_self_aura`,
     `requires_ranged_range`)
SELECT `profile`.`id`, `apl`.`sort_order`, `apl`.`spell_id`, `apl`.`category`,
       `apl`.`mechanic_tags`, `apl`.`damage_weight`, `apl`.`survival_weight`,
       `apl`.`priority_bucket`, `apl`.`min_enemies`, `apl`.`max_enemies`,
       `apl`.`target_selector`, `apl`.`movement_directive`,
       `apl`.`auto_attack_mode`, `apl`.`min_range`, `apl`.`max_range`,
       `apl`.`maintain_aura_id`, `apl`.`required_self_aura`,
       `apl`.`requires_ranged_range`
FROM `bot_rotation_profile` AS `profile`
CROSS JOIN (
    SELECT 25 AS `sort_order`, 603 AS `spell_id`, 'dot' AS `category`,
           'bane_of_doom,dot,pinned_apl' AS `mechanic_tags`,
           0.98 AS `damage_weight`, 0.00 AS `survival_weight`,
           1 AS `priority_bucket`, 1 AS `min_enemies`, 1 AS `max_enemies`,
           'enemy' AS `target_selector`, 'ranged' AS `movement_directive`,
           'none' AS `auto_attack_mode`, 5 AS `min_range`, 35 AS `max_range`,
           603 AS `maintain_aura_id`, 0 AS `required_self_aura`,
           1 AS `requires_ranged_range`
    UNION ALL
    SELECT 45, 50589, 'aoe',
           'immolation_aura,metamorphosis,pinned_apl',
           0.96, 0.05, 1, 1, 0, 'self', 'ranged', 'none', 0, 0,
           50589, 59672, 0
    UNION ALL
    SELECT 55, 47897, 'spender',
           'shadowflame,short_range,pinned_apl',
           0.90, 0.00, 2, 1, 0, 'enemy', 'ranged', 'none', 0, 10,
           0, 0, 0
    UNION ALL
    SELECT 75, 29722, 'builder',
           'incinerate,filler,pinned_apl',
           0.82, 0.00, 4, 1, 0, 'enemy', 'ranged', 'none', 5, 35,
           0, 0, 1
) AS `apl`
WHERE `profile`.`class_id` = 9
  AND `profile`.`spec_tag` = 'demonology_warlock'
  AND `profile`.`role` = 'dps'
  AND NOT EXISTS (
      SELECT 1
      FROM `bot_rotation_action` AS `existing`
      WHERE `existing`.`profile_id` = `profile`.`id`
        AND `existing`.`spell_id` = `apl`.`spell_id`
  );

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`enabled` = 0
WHERE `profile`.`class_id` = 9
  AND `profile`.`spec_tag` = 'demonology_warlock'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 686;
