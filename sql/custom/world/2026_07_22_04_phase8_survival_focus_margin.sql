-- Phase 8 Survival qualification adds a small live-cadence safety margin over
-- the hard reference floor by allowing the focus dump slightly before the
-- simulator's idealized 69-focus threshold.

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`min_primary_power_pct` = 0.65,
    a.`mechanic_tags` = 'arcane_shot,focus_dump,live_cadence_at_or_above_65_focus'
WHERE p.`class_id` = 3
  AND p.`spec_tag` = 'survival'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 3044;

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 10),
    `source_note` = 'phase8_survival_focus_margin_2026_07_22',
    `scope_note` = 'Live decision-cadence focus dump margin while preserving the pinned rotation authority'
WHERE `class_id` = 3
  AND `spec_tag` = 'survival'
  AND `role` = 'dps';
