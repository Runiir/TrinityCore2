-- Affliction's promoted APL spends its second Volcanic Potion in execute.
-- Keep the action self-targeted while evaluating the hostile target's health,
-- and let native inventory, item cooldown, and raid reservation policy decide
-- whether the real item can be submitted.

UPDATE `bot_rotation_profile`
SET `version` = CASE WHEN `version` < 4 THEN 4 ELSE `version` END,
    `source_note` = 'wowsims_affliction_apl_player_actions_v2',
    `scope_note` = 'typed live-state approximation including execute combat potion'
WHERE `class_id` = 9
  AND `spec_tag` = 'affliction_warlock'
  AND `role` = 'dps';

DELETE FROM `bot_rotation_action`
WHERE `spell_id` = 79476
  AND `profile_id` IN (
      SELECT `id`
      FROM `bot_rotation_profile`
      WHERE `class_id` = 9
        AND `spec_tag` = 'affliction_warlock'
        AND `role` = 'dps'
  );

INSERT INTO `bot_rotation_action`
    (`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
     `damage_weight`, `survival_weight`, `priority_bucket`, `min_enemies`,
     `max_enemies`, `min_target_health_pct`, `max_target_health_pct`,
     `target_selector`, `movement_directive`, `auto_attack_mode`, `min_range`,
     `max_range`, `maintain_aura_id`, `min_mana_pct`, `max_mana_pct`,
     `max_hostile_target_health_pct`, `enabled`)
SELECT `profile`.`id`, 75, 79476, 'use_item',
       'volcanic_potion,combat_potion,execute_25,pinned_apl',
       1.10, 0.00, 7, 1, 0, 0.00, 1.00,
       'self', 'ranged', 'none', 0, 0, 0, 0.00, 1.00, 0.25, 1
FROM `bot_rotation_profile` AS `profile`
WHERE `profile`.`class_id` = 9
  AND `profile`.`spec_tag` = 'affliction_warlock'
  AND `profile`.`role` = 'dps';
