-- Blood Death Knight tank: cast native Rune Tap below 60% health.
--
-- Why (error ledger TANK-003). In b3-0dbce440-k1 on Magmaw 10N, the sole
-- Blood tank, actor 30002 (Mgwtankb), met the 90 s Mangle at 46% health with
-- no cooldown left and died to it at 89.2 s. The profile has no Rune Tap row,
-- although 48982 is provisioned. The Magmaw Mangle cooldown plan
-- (BotMagmawMangleCooldownPlan.h) spends Vampiric Blood or Rune Tap at 35%
-- health instead of Icebound Fortitude, so Icebound is still there for
-- Mangle. Rune Tap is the repeatable heal in that plan. WCL Nexry
-- (Y8ajQ7dbmKMG1RZy fight 22, 10N) casts Rune Tap at 97.2 s, during the
-- first Mangle seize.
--
-- Native facts from the pinned 4.3.4 DBC:
--   * Rune Tap 48982: power type runes. SpellRuneCost 581 is 1 Blood rune,
--     no Unholy, no Frost, no runic power gain. A Death rune can pay for the
--     Blood rune (Spell::CheckRuneCost).
--   * Effect 0 is HEAL_PCT (136) for 10: 10% of maximum health. No aura.
--   * Cooldown 30 s (SpellCooldowns RecoveryTime 30000). Off the global
--     cooldown: StartRecoveryTime 0, StartRecoveryCategory 0.
--   * Will of the Necropolis (52284, provisioned; spell_dk_will_of_the_
--     necropolis): damage that takes the tank below 30% resets Rune Tap's
--     cooldown and applies 96171 for 8 s. 96171 is ADD_PCT_MODIFIER -100 on
--     PowerCost0 for class mask 0x08000000, which is Rune Tap's family
--     flag, so the next Rune Tap costs no rune. The candidate builder
--     (HasEnoughPowerForProfileSpell) applies the same PowerCost0 modifier,
--     so the row needs no ready-rune floor. min_ready_runes is 0, so the free
--     cast is not rejected with 0 runes ready.
-- This row adds no aura, proc, damage multiplier, forced cast, resource or
-- cooldown change beyond the native spell.
--
-- Gate. max_self_health_pct 0.6: only below 60% health.
--
-- Priority. The candidate base score is the weight sum minus bucket * 0.03.
-- For H2.0/T1.2/S0.35 in bucket 1 it is 3.52. The resolver then adds a
-- per-mode term:
--   balanced_role_dps 4.32    above Heart Strike 4.17, Rune Strike 4.155 and
--                             Blood Tap 4.205; below Empower Rune Weapon
--                             4.425 and Death Strike 4.5855
--   role_first (tank) 4.8775  above Heart Strike 4.47 and Rune Strike 4.52;
--                             below Death Strike 5.5625
--   dps_push          3.52    below the strikes and Death Strike 4.54
--   pure_survival     6.045   above Vampiric Blood 4.87 and Icebound
--                             Fortitude 4.57; below Death Strike 6.315
-- Death Strike outranks it in every mode, so a castable Death Strike (a
-- bigger heal and a Blood Shield) always goes first. The tank's retained
-- trace ran balanced_role_dps. There Rune Tap goes before Heart Strike. It is
-- off the GCD, so it also fits windows where every GCD action is rejected
-- with global_cooldown. The weights are chosen to place these scores. There
-- is no damage weight: the spell deals no damage. The threat weight stands
-- for the native healing threat, half the effective heal (Spell.cpp
-- ForwardThreatForAssistingMe).
-- Category defensive: the raid reservation exempts it on trash
-- (IsEmergencyOrSurvival). Its 30 s cooldown is shorter than the 90 s
-- opening Mangle and the 95 s Mangle spacing, so BossDefensiveReservationReason
-- never holds it.
--
-- Provisioning dependency. 48982 is listed in
-- action_profile_spells_by_spec.blood_death_knight in
-- experiments/configs/cata_434_action_profiles.json. Without it the row is
-- rejected as unknown_requested_spell and changes nothing.
--
-- The migration is idempotent. The insert is guarded by NOT EXISTS, and the
-- version bump never lowers the version. The reverse migration is a
-- commented block at the end of this file, not a separate file: the
-- worldserver auto-updater applies every file in sql/custom/world at
-- startup, so a separate revert file would undo this one immediately.

INSERT INTO `bot_rotation_action`
    (`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
     `damage_weight`, `healing_weight`, `threat_weight`, `mitigation_weight`,
     `survival_weight`, `priority_bucket`, `min_enemies`, `max_enemies`,
     `max_self_health_pct`, `requires_melee_range`, `target_selector`,
     `movement_directive`, `auto_attack_mode`, `min_range`, `max_range`,
     `maintain_aura_id`, `refresh_aura_below_ms`, `min_ready_runes`,
     `max_ready_runes`, `enabled`)
SELECT `profile`.`id`, 29, 48982, 'defensive',
       'rune_tap,self_heal,blood_rune,off_gcd',
       0, 2.0, 1.2, 0,
       0.35, 1, 1, 0,
       0.6, 0, 'self',
       'melee', 'melee', 0, 0,
       0, 0, 0,
       0, 1
FROM `bot_rotation_profile` AS `profile`
WHERE `profile`.`class_id` = 6
  AND `profile`.`spec_tag` = 'blood_death_knight'
  AND `profile`.`role` = 'tank'
  AND NOT EXISTS (
      SELECT 1 FROM `bot_rotation_action` AS `existing`
      WHERE `existing`.`profile_id` = `profile`.`id`
        AND `existing`.`spell_id` = 48982
  );

UPDATE `bot_rotation_profile`
SET `version` = CASE WHEN `version` < 32 THEN 32 ELSE `version` END,
    `source_note` = 'phase9_blood_rune_tap_2026_09_24',
    `scope_note` = 'Cast native Rune Tap below 60% health, above Heart Strike and below Death Strike'
WHERE `class_id` = 6
  AND `spec_tag` = 'blood_death_knight'
  AND `role` = 'tank';

-- BEGIN REVERSE MIGRATION
-- DELETE FROM `bot_rotation_action`
-- WHERE `profile_id` IN (
--     SELECT `id` FROM `bot_rotation_profile`
--     WHERE `class_id` = 6
--       AND `spec_tag` = 'blood_death_knight'
--       AND `role` = 'tank'
--   )
--   AND `spell_id` = 48982
--   AND `sort_order` = 29
--   AND `mechanic_tags` = 'rune_tap,self_heal,blood_rune,off_gcd';
-- UPDATE `bot_rotation_profile`
-- SET `version` = 31,
--     `source_note` = 'phase9_blood_empower_rune_weapon_rune_recovery_2026_09_23',
--     `scope_note` = 'Cast native Empower Rune Weapon only while at most one rune is ready, above Blood Tap and below Death Strike'
-- WHERE `class_id` = 6
--   AND `spec_tag` = 'blood_death_knight'
--   AND `role` = 'tank'
--   AND `source_note` = 'phase9_blood_rune_tap_2026_09_24';
-- END REVERSE MIGRATION
