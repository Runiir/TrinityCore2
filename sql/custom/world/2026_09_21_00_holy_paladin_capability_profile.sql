-- HEAL-001: expose the first native Holy Paladin Holy Power spender.
-- The candidate builder owns the holy_power_3 resource gate; this migration
-- only supplies the missing profile action and its existing healer triage gate.
INSERT INTO `bot_rotation_action` (
    `profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
    `damage_weight`, `healing_weight`, `survival_weight`, `priority_bucket`,
    `min_enemies`, `max_target_health_pct`, `target_selector`,
    `movement_directive`, `auto_attack_mode`, `max_range`, `maintain_aura_id`,
    `min_injured_players`, `injured_health_pct`
)
SELECT
    `profile`.`id`, 15, 85673, 'heal_fast',
    'word_of_glory,holy_power_3,triage,heal',
    0, 1.00, 0.90, 1,
    1, 0.94, 'lowest_ally', 'healer_support', 'none', 40, 0,
    1, 0.94
FROM `bot_rotation_profile` AS `profile`
WHERE `profile`.`class_id` = 2
  AND `profile`.`spec_tag` = 'holy_paladin'
  AND `profile`.`role` = 'healer'
  AND `profile`.`enabled` = 1
  AND NOT EXISTS (
      SELECT 1
      FROM `bot_rotation_action` AS `existing`
      WHERE `existing`.`profile_id` = `profile`.`id`
        AND `existing`.`spell_id` = 85673
        AND `existing`.`category` = 'heal_fast'
  );
