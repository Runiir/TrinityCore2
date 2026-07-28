-- Phase 8 Assassination qualification keeps the passing single-target
-- priority authoritative when multiple enemies are present. Fan of Knives
-- remains available only as a lowest-priority, high-energy fallback.

DELETE a FROM `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
WHERE p.`class_id` = 4
  AND p.`spec_tag` = 'assassination_rogue'
  AND p.`role` = 'dps'
  AND a.`mechanic_tags` IN (
    'mutilate,aoe_rupture_builder,combo_builder',
    'rupture,aoe_primary,venomous_wounds'
  );

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`max_enemies` = 0
WHERE p.`class_id` = 4
  AND p.`spec_tag` = 'assassination_rogue'
  AND p.`role` = 'dps'
  AND a.`max_enemies` = 1;

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`priority_bucket` = 9,
    a.`min_primary_power_pct` = 0.85
WHERE p.`class_id` = 4
  AND p.`spec_tag` = 'assassination_rogue'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 51723
  AND a.`mechanic_tags` = 'fan_of_knives,aoe,poison_application';

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 8),
    `source_note` = 'phase8_assassination_primary_target_qualification_2026_07_22',
    `scope_note` = 'Single-target Mutilate Rupture Envenom priority remains authoritative during multi-target combat'
WHERE `class_id` = 4
  AND `spec_tag` = 'assassination_rogue'
  AND `role` = 'dps';
