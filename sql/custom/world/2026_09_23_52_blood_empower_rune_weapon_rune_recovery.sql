-- Blood Death Knight tank: cast native Empower Rune Weapon while runes are
-- short.
--
-- Evidence, r3-47cd175 kill 5, Magmaw 10N, actor 30002 (Mgwtankb). The
-- profile has no Empower Rune Weapon row and 47568 was not provisioned. The
-- tank is rune-starved: Death Strike failed its min_ready_runes 2 gate 1,715
-- times, and 10 Death Strikes landed against 18 for WCL Nexry
-- (Y8ajQ7dbmKMG1RZy fight 22). Nexry casts Empower Rune Weapon once, at
-- 12.7 s.
--
-- Native facts from the pinned 4.3.4 DBC:
--   * Empower Rune Weapon 47568 costs no rune. SpellRuneCost gives 25
--     runic power (RunicPowerGain 250).
--   * Cooldown 300 s, so at most one per kill. Off the global cooldown:
--     StartRecoveryTime 0, StartRecoveryCategory 0.
--   * Effect 0 is ACTIVATE_RUNE (146) for 2 Blood, effect 1 is
--     ACTIVATE_RUNE for 2 Frost, and effect 2 triggers 89831. 89831 is
--     ACTIVATE_RUNE for 6 Death-or-Blood-base runes and ACTIVATE_RUNE for 2
--     Unholy. Spell::EffectActivateRune only ends cooldowns that are
--     running, so every recharging rune becomes ready. Ready runes are
--     untouched.
-- This row adds no aura, proc, damage multiplier, forced cast or resource
-- beyond the native spell.
--
-- Gate. max_ready_runes 1, from 2026_09_23_50, allows the row only when at
-- most one of the six runes is ready, so at least five runes are recharged.
-- Death Strike needs min_ready_runes 2. In the same decision, a valid Empower
-- Rune Weapon and a valid Death Strike cannot coexist: it never displaces a
-- castable Death Strike.
--
-- Priority. The candidate base score is the weight sum minus bucket * 0.03.
-- For D1.1/T2.2 in bucket 1 it is 3.27. The resolver then adds a per-mode
-- term:
--   balanced_role_dps 4.425  above Blood Tap 4.205, Heart Strike 4.17 and
--                            Rune Strike 4.155; below Death Strike 4.5855
--   role_first (tank) 5.47   above Blood Tap 4.97; below Death Strike 5.5625
--   dps_push          4.37   above Blood Tap 4.27; below Death Strike 4.54
--   pure_survival     2.995  above Blood Tap 2.77; below Death Strike 6.315
-- It outranks Blood Tap in every mode. When both are valid, Empower Rune
-- Weapon refreshes every rune first. Blood Tap is then held by its own cap
-- until runes are short again, and its 30 s cooldown is not spent on a rune
-- Empower Rune Weapon would have refreshed.
--
-- Category offensive_cooldown, as the Unholy Empower Rune Weapon row and
-- Dancing Rune Weapon use. BotRaidCooldownReservation holds that category on
-- raid trash, regroup and pre-pull (raid_offensive_cooldown_reserved), so
-- the 300 s cooldown is still ready when Magmaw is pulled.
--
-- Provisioning dependency. 47568 is listed in
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
SELECT `profile`.`id`, 36, 47568, 'offensive_cooldown',
       'empower_rune_weapon,rune_activation,runic_power,runes_short,off_gcd',
       1.1, 0, 2.2, 0,
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
        AND `existing`.`spell_id` = 47568
  );

UPDATE `bot_rotation_profile`
SET `version` = CASE WHEN `version` < 31 THEN 31 ELSE `version` END,
    `source_note` = 'phase9_blood_empower_rune_weapon_rune_recovery_2026_09_23',
    `scope_note` = 'Cast native Empower Rune Weapon only while at most one rune is ready, above Blood Tap and below Death Strike'
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
--   AND `spell_id` = 47568
--   AND `sort_order` = 36
--   AND `mechanic_tags` = 'empower_rune_weapon,rune_activation,runic_power,runes_short,off_gcd';
-- UPDATE `bot_rotation_profile`
-- SET `version` = 30,
--     `source_note` = 'phase9_blood_tap_rune_recovery_2026_09_23',
--     `scope_note` = 'Cast native Blood Tap only while at most one rune is ready, below Death Strike in every balance mode'
-- WHERE `class_id` = 6
--   AND `spec_tag` = 'blood_death_knight'
--   AND `role` = 'tank'
--   AND `source_note` = 'phase9_blood_empower_rune_weapon_rune_recovery_2026_09_23';
-- END REVERSE MIGRATION
