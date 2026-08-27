-- Restore the mobile single-target response for the canonical Holy Paladin and
-- Discipline Priest healer profiles.  The profile only exposes real spells;
-- native known-spell, mana, aura, GCD, range, LOS, and cast submission checks
-- remain authoritative.

DELETE `action`
FROM `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id` = `action`.`profile_id`
WHERE (`profile`.`class_id`, `profile`.`spec_tag`, `profile`.`role`, `action`.`spell_id`) IN (
  (2, 'holy_paladin', 'healer', 20473),
  (5, 'discipline_priest', 'healer', 17)
);

INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
 `healing_weight`, `survival_weight`, `priority_bucket`, `max_target_health_pct`,
 `forbidden_target_aura`, `target_selector`, `movement_directive`,
 `auto_attack_mode`, `max_range`, `requires_instant_cast`, `maintain_aura_id`,
 `min_injured_players`, `injured_health_pct`)
VALUES
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=2 AND `spec_tag`='holy_paladin' AND `role`='healer'), 15, 20473, 'heal_fast', 'holy_shock,triage,instant', 1.00, 0.85, 0, 0.94, 0, 'lowest_ally', 'healer_support', 'none', 40, 1, 0, 1, 0.94),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=5 AND `spec_tag`='discipline_priest' AND `role`='healer'), 5, 17, 'heal_fast', 'power_word_shield,absorb,instant,triage', 1.35, 1.00, 0, 0.94, 6788, 'lowest_ally', 'healer_support', 'none', 40, 1, 17, 1, 0.94);
