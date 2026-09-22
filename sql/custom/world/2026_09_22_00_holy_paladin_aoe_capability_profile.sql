-- HEAL-001: expose the native Holy Paladin multi-target healing path.
-- The resolver/policy already own AoeHeal; this migration only supplies the
-- missing profile action and retains the existing Holy Power and triage gates.
INSERT INTO `bot_rotation_action` (
    `profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
    `damage_weight`, `healing_weight`, `survival_weight`, `priority_bucket`,
    `min_enemies`, `max_target_health_pct`, `target_selector`,
    `movement_directive`, `auto_attack_mode`, `max_range`, `maintain_aura_id`,
    `min_injured_players`, `injured_health_pct`
)
SELECT
    `profile`.`id`, 12, 85222, 'heal_aoe',
    'light_of_dawn,aoe,heal,holy_power_3',
    0, 1.00, 0.85, 1,
    1, 0.70, 'lowest_ally', 'healer_support', 'none', 40, 0,
    3, 0.70
FROM `bot_rotation_profile` AS `profile`
WHERE `profile`.`class_id` = 2
  AND `profile`.`spec_tag` = 'holy_paladin'
  AND `profile`.`role` = 'healer'
  AND `profile`.`enabled` = 1
  AND NOT EXISTS (
      SELECT 1
      FROM `bot_rotation_action` AS `existing`
      WHERE `existing`.`profile_id` = `profile`.`id`
        AND `existing`.`spell_id` = 85222
        AND `existing`.`category` = 'heal_aoe'
  );
