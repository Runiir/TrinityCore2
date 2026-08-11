-- Phase 8 deterministic healer qualification requires each canonical healer
-- profile to expose a real dispel and a real cooldown through SQL authority.

DELETE a FROM `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
WHERE (p.`class_id`, p.`spec_tag`, p.`role`, a.`spell_id`) IN (
  (2, 'holy_paladin', 'healer', 4987),
  (2, 'holy_paladin', 'healer', 31842),
  (5, 'discipline_priest', 'healer', 527),
  (5, 'discipline_priest', 'healer', 33206),
  (7, 'restoration_shaman', 'healer', 98008),
  (11, 'restoration_druid', 'healer', 88423),
  (11, 'restoration_druid', 'healer', 33891)
);

INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`, `healing_weight`, `survival_weight`, `priority_bucket`, `min_injured_players`, `injured_health_pct`, `target_selector`, `movement_directive`, `auto_attack_mode`, `max_range`, `maintain_aura_id`) VALUES
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=2 AND `spec_tag`='holy_paladin' AND `role`='healer'), 40, 4987, 'dispel_cleanse', 'cleanse,dispel', 0.20, 0.65, 1, 1, 1.00, 'lowest_ally', 'healer_support', 'none', 40, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=2 AND `spec_tag`='holy_paladin' AND `role`='healer'), 50, 31842, 'offensive_cooldown', 'divine_favor,healing_cooldown', 0.85, 0.85, 1, 1, 0.65, 'self', 'healer_support', 'none', 40, 31842),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=5 AND `spec_tag`='discipline_priest' AND `role`='healer'), 60, 527, 'dispel_cleanse', 'purify,dispel', 0.20, 0.65, 1, 1, 1.00, 'lowest_ally', 'healer_support', 'none', 40, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=5 AND `spec_tag`='discipline_priest' AND `role`='healer'), 70, 33206, 'external_defensive', 'pain_suppression,healing_cooldown', 0.20, 1.00, 1, 1, 0.65, 'lowest_ally', 'healer_support', 'none', 40, 33206),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=7 AND `spec_tag`='restoration_shaman' AND `role`='healer'), 70, 98008, 'defensive', 'spirit_link_totem,healing_cooldown', 0.85, 1.00, 1, 1, 0.65, 'self', 'healer_support', 'none', 40, 98008),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=11 AND `spec_tag`='restoration_druid' AND `role`='healer'), 50, 88423, 'dispel_cleanse', 'natures_cure,dispel', 0.20, 0.65, 1, 1, 1.00, 'lowest_ally', 'healer_support', 'none', 40, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=11 AND `spec_tag`='restoration_druid' AND `role`='healer'), 60, 33891, 'offensive_cooldown', 'tree_of_life,healing_cooldown', 0.85, 1.00, 1, 1, 0.65, 'self', 'healer_support', 'none', 40, 33891);

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`healing_weight` = 1.25, a.`priority_bucket` = 1
WHERE p.`class_id` = 7 AND p.`spec_tag` = 'restoration_shaman' AND p.`role` = 'healer'
  AND a.`spell_id` = 1064;
