-- Phase 8 Survival qualification aligns the live candidate with the pinned
-- numeric simulator fixture's Orc race and autocast-other-cooldowns behavior.

DELETE a FROM `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
WHERE p.`class_id` = 3
  AND p.`spec_tag` = 'survival'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 20572;

INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
 `damage_weight`, `survival_weight`, `priority_bucket`, `min_enemies`, `max_enemies`,
 `max_target_health_pct`, `target_selector`, `movement_directive`, `auto_attack_mode`,
 `min_range`, `max_range`, `cooldown_group`)
VALUES
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 3 AND `spec_tag` = 'survival' AND `role` = 'dps'),
 15, 20572, 'offensive_cooldown', 'blood_fury,self,orc_fixture,autocast_other_cooldowns',
 0.95, 0.00, 1, 1, 1, 1.00, 'self', 'ranged', 'ranged', 0, 0, 'blood_fury');

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 9),
    `source_note` = 'phase8_survival_orc_fixture_2026_07_22',
    `scope_note` = 'Pinned Orc numeric fixture with Blood Fury and exact ferocity pet talents'
WHERE `class_id` = 3
  AND `spec_tag` = 'survival'
  AND `role` = 'dps';
