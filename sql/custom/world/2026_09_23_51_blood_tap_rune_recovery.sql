-- Blood Death Knight tank: cast native Blood Tap while runes are short.
--
-- Evidence, r3-47cd175 kill 5, Magmaw 10N, actor 30002 (Mgwtankb). The
-- profile has no Blood Tap row and 45529 was not provisioned. The tank is
-- rune-starved: Death Strike failed its min_ready_runes 2 gate 1,715 times
-- and Heart Strike failed its gate 1,021 times, and 10 Death Strikes landed
-- against 18 for WCL Nexry (Y8ajQ7dbmKMG1RZy fight 22). Nexry casts Blood
-- Tap at 7.1, 39.2 and 76.9 s.
--
-- Native facts from the pinned 4.3.4 DBC:
--   * Blood Tap 45529 costs no rune or runic power. Its power type is
--     health with SpellPower ManaCostPercentage 6, and
--     SpellInfo::CalcPowerCost bases that on GetCreateHealth: 6% of base
--     health.
--   * Cooldown 60 s. Improved Blood Tap rank 2, 94555 (provisioned), takes 30 s
--     off it through a flat cooldown modifier on class mask 0x8, which is
--     Blood Tap's family flag. Net cooldown 30 s.
--   * Off the global cooldown: StartRecoveryTime 0, StartRecoveryCategory 0.
--   * Effect 0 is ACTIVATE_RUNE (146) for 1 rune, type Death.
--     Spell::EffectActivateRune ends the cooldown of the first rune on
--     cooldown whose current type is Death or whose base type is Blood.
--     Ready runes are untouched. Effect 1 is CONVERT_RUNE (249): one Blood
--     rune becomes a Death rune for 20 s.
-- This row adds no aura, proc, damage multiplier, forced cast or resource.
--
-- Gate. max_ready_runes 1, from 2026_09_23_50, allows the row only when at
-- most one of the six runes is ready. Then at least one of the two Blood-slot
-- runes is on cooldown, so the activation always lands on a recharging rune.
-- Death Strike needs min_ready_runes 2. In the same decision, a valid Blood
-- Tap and a valid Death Strike cannot coexist: Blood Tap never displaces a
-- castable Death Strike.
--
-- Priority. The candidate base score is the weight sum minus bucket * 0.03.
-- For D1.2/T1.9 in bucket 1 it is 3.07. The resolver then adds a per-mode
-- term:
--   balanced_role_dps 4.205  above Heart Strike 4.17 and Rune Strike 4.155;
--                            below Empower Rune Weapon 4.425 and Death Strike
--                            4.5855
--   role_first (tank) 4.97   below ERW 5.47 and Death Strike 5.5625
--   dps_push          4.27   below ERW 4.37 and Death Strike 4.54
--   pure_survival     2.77   below ERW 2.995 and Death Strike 6.315
-- The tank's retained trace ran balanced_role_dps. Blood Tap is off the GCD,
-- so it also fits into GCD windows where every on-GCD action is rejected
-- with global_cooldown.
-- Category resource_generator, as the Frost and Unholy Blood Tap rows use.
-- Raid cooldown reservation does not hold it; a 30 s cooldown needs no
-- boss reservation.
--
-- Provisioning dependency. 45529 is listed in
-- action_profile_spells_by_spec.blood_death_knight in
-- experiments/configs/cata_434_action_profiles.json. Without it the row is
-- rejected as unknown_requested_spell and changes nothing.
--
-- The migration is idempotent. The insert is guarded by NOT EXISTS and the
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
SELECT `profile`.`id`, 37, 45529, 'resource_generator',
       'blood_tap,rune_activation,death_rune,runes_short,off_gcd',
       1.2, 0, 1.9, 0,
       0, 1, 1, 0,
       1.0, 0, 'self',
       'melee', 'melee', 0, 0,
       0, 0, 0,
       1, 1
FROM `bot_rotation_profile` AS `profile`
WHERE `profile`.`class_id` = 6
  AND `profile`.`spec_tag` = 'blood_death_knight'
  AND `profile`.`role` = 'tank'
  AND NOT EXISTS (
      SELECT 1 FROM `bot_rotation_action` AS `existing`
      WHERE `existing`.`profile_id` = `profile`.`id`
        AND `existing`.`spell_id` = 45529
  );

UPDATE `bot_rotation_profile`
SET `version` = CASE WHEN `version` < 30 THEN 30 ELSE `version` END,
    `source_note` = 'phase9_blood_tap_rune_recovery_2026_09_23',
    `scope_note` = 'Cast native Blood Tap only while at most one rune is ready, below Death Strike in every balance mode'
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
--   AND `spell_id` = 45529
--   AND `sort_order` = 37
--   AND `mechanic_tags` = 'blood_tap,rune_activation,death_rune,runes_short,off_gcd';
-- UPDATE `bot_rotation_profile`
-- SET `version` = 29,
--     `source_note` = 'phase9_blood_outbreak_disease_upkeep_2026_09_23',
--     `scope_note` = 'Maintain Blood Plague and Frost Fever with native Outbreak, keeping Icy Touch and Plague Strike as cooldown fallbacks'
-- WHERE `class_id` = 6
--   AND `spec_tag` = 'blood_death_knight'
--   AND `role` = 'tank'
--   AND `source_note` = 'phase9_blood_tap_rune_recovery_2026_09_23';
-- END REVERSE MIGRATION
