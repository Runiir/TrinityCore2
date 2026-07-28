-- Phase 8 Survival qualification restores the proven one-shot scored opener
-- trap after repeatable placement failed to reactivate on the stationary dummy.
-- Black Arrow resumes shared-cooldown maintenance after the opener.

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`sort_order` = 17,
    a.`priority_bucket` = 1,
    a.`required_self_aura` = 2825,
    a.`min_self_aura_remaining_ms` = 30000,
    a.`mechanic_tags` = 'explosive_trap,single_target,scored_opener,lock_and_load'
WHERE p.`class_id` = 3
  AND p.`spec_tag` = 'survival'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 13813
  AND a.`min_enemies` = 1
  AND a.`max_enemies` = 1;

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 16),
    `source_note` = 'phase8_survival_opener_trap_restore_2026_07_22',
    `scope_note` = 'One scored opener Explosive Trap followed by Black Arrow maintenance'
WHERE `class_id` = 3
  AND `spec_tag` = 'survival'
  AND `role` = 'dps';
