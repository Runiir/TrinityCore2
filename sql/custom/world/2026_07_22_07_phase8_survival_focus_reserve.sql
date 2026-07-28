-- Phase 8 Survival qualification restores the productive opener Rapid Fire
-- timing proven with the exact Orc/ferocity-pet fixture and reserves enough
-- focus for the following 500 ms decision after a sustained Arcane Shot dump.

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`forbidden_self_aura` = 0,
    a.`priority_bucket` = 2,
    a.`mechanic_tags` = 'rapid_fire,opener,cooldown,heroism_burst'
WHERE p.`class_id` = 3
  AND p.`spec_tag` = 'survival'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 3045;

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`min_primary_power_pct` = 0.75,
    a.`mechanic_tags` = 'arcane_shot,focus_dump,live_cadence_reserve_at_or_above_75_focus'
WHERE p.`class_id` = 3
  AND p.`spec_tag` = 'survival'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 3044
  AND a.`sort_order` = 70;

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 13),
    `source_note` = 'phase8_survival_focus_reserve_2026_07_22',
    `scope_note` = 'Productive opener Rapid Fire and 75-focus live-cadence reserve before sustained Arcane Shot'
WHERE `class_id` = 3
  AND `spec_tag` = 'survival'
  AND `role` = 'dps';
