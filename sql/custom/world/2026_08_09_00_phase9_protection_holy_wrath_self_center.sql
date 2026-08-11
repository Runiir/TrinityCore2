-- Phase 9 rerun189 localized Protection's longest Azil healer-target
-- episodes to movement toward a changing follower representative while the
-- native Holy Wrath action was ready. Holy Wrath is centered on the caster;
-- describe that native target topology so the existing self-centered area
-- readiness gate can cast it from useful ten-yard coverage instead of
-- requiring enemy melee range. No priority, threshold, cooldown, threat, or
-- victim rule changes.
UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`target_selector` = 'self'
WHERE p.`class_id` = 2
  AND p.`spec_tag` = 'protection'
  AND p.`role` = 'tank'
  AND a.`spell_id` = 2812;

UPDATE `bot_rotation_profile`
SET `version` = `version` + 1,
    `source_note` = 'phase9_rerun190_holy_wrath_self_center_2026_08_09',
    `scope_note` = 'Protection native Holy Wrath caster-centered area topology'
WHERE `class_id` = 2
  AND `spec_tag` = 'protection'
  AND `role` = 'tank';
