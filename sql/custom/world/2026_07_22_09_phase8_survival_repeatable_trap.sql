-- Phase 8 Survival qualification uses Explosive Trap on each single-target
-- shared-cooldown cycle. TrinityCore marks trap activation for Lock and Load,
-- giving the exact rank-two fixture a deterministic proc opportunity instead
-- of relying only on Black Arrow tick variance. Explosive Shot remains first
-- among ready damage actions; the trap follows it and suppresses Black Arrow
-- through their normal shared cooldown.

UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`sort_order` = 21,
    a.`priority_bucket` = 1,
    a.`required_self_aura` = 0,
    a.`min_self_aura_remaining_ms` = 0,
    a.`mechanic_tags` = 'explosive_trap,single_target,repeatable,deterministic_lock_and_load'
WHERE p.`class_id` = 3
  AND p.`spec_tag` = 'survival'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 13813
  AND a.`min_enemies` = 1
  AND a.`max_enemies` = 1;

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 15),
    `source_note` = 'phase8_survival_repeatable_trap_2026_07_22',
    `scope_note` = 'Repeatable single-target Explosive Trap for deterministic Lock and Load opportunities'
WHERE `class_id` = 3
  AND `spec_tag` = 'survival'
  AND `role` = 'dps';
