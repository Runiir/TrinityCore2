-- Blood Death Knight tank: keep diseases up with native Outbreak.
--
-- Evidence, base-0891a99 kills 1-3, Magmaw 10N, actor 30002. The profile has
-- no Outbreak row. Icy Touch and Plague Strike apply the diseases, and they
-- are the two lowest-scoring valid bucket-1 actions (balanced_role_dps 3.10
-- and 3.04, against Death Strike 4.59, Heart Strike 4.17 and Rune Strike 4.16).
-- As a result:
--   * Blood Plague lands 22/38, 31/36 and 25/37 possible ticks. It is absent
--     for the first 33 s of kill 1 and the first 35 s of kill 3.
--   * 11, 6 and 9 Heart Strikes land without both diseases.
--   * 5, 6 and 7 Frost/Unholy runes, with their GCDs, go to Icy Touch and
--     Plague Strike instead of Death Strike. The bot is rune-starved: Death
--     Strike fails its rune gate on 78-89% of evaluations.
-- WCL Nexry (Y8ajQ7dbmKMG1RZy fight 22) casts Outbreak at 4.1, 37.0 and
-- 70.2 s, and never casts Icy Touch or Plague Strike.
--
-- Native facts from the pinned 4.3.4 DBC:
--   * Outbreak 77575 has no rune or power cost, a 30 yd range, a 1.5 s GCD
--     and a 60 s cooldown.
--   * Veteran of the Third War 50029 (provisioned) takes 30 s off it through
--     class mask 0x1000.
--   * Epidemic 81334 (provisioned) extends Blood Plague 55078 and Frost Fever
--     55095 from 21 s to 33 s.
--   * Outbreak only triggers the two single-target disease auras. It has no
--     chain, area or rune-conversion effect.
-- One Outbreak every 30 s therefore keeps both diseases up without spending
-- runes. This migration adds no aura, proc, damage multiplier, forced cast
-- or resource.
--
-- Priority. The base score is the weight sum minus bucket*0.03, which for
-- D1.8/T1.7 in bucket 1 is 3.47. The resolver then adds a per-mode term:
--   balanced_role_dps 4.885  above Death Strike 4.586, Heart Strike 4.17 and
--                             Rune Strike 4.155; below Dark Command 5.27 and
--                             Dancing Rune Weapon 5.82
--   role_first (tank) 5.17   below Death Strike 5.5625 (survival first)
--   dps_push          5.27   above Death Strike 4.54, below DRW 6.22
--   pure_survival     3.02   below Death Strike 6.315
-- Icy Touch and Plague Strike are unchanged. They remain fallbacks while
-- Outbreak is on cooldown.
--
-- Provisioning dependency. The bot knows only the spells provisioned from
-- experiments/configs/cata_434_action_profiles.json, and
-- PlayerStart.AllSpells is 0. 77575 is listed in
-- action_profile_spells_by_spec.blood_death_knight (as for Frost and
-- Unholy); without it this row is rejected as unknown_requested_spell and
-- changes nothing.
--
-- Re-promotion. This file was applied once (updates hash 7410d1a), then
-- un-promoted, and its row was deleted by hand. The auto-updater skips a
-- file whose name and hash are both recorded, so the unchanged file would
-- never re-insert the row. Since then 2026_09_23_40/41 took the profile to
-- version 28. This revision bumps to 29 and its reverse block restores the
-- 2026_09_23_41 identity; the changed hash makes the updater reapply the
-- file, and the NOT EXISTS guard keeps that replay idempotent.
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
     `maintain_aura_id`, `refresh_aura_below_ms`, `min_ready_runes`, `enabled`)
SELECT `profile`.`id`, 38, 77575, 'debuff',
       'outbreak,diseases,blood_plague,frost_fever,maintain_owned_aura,no_rune_cost',
       1.8, 0, 1.7, 0,
       0, 1, 1, 0,
       1.0, 0, 'enemy',
       'melee', 'melee', 0, 0,
       55078, 3000, 0, 1
FROM `bot_rotation_profile` AS `profile`
WHERE `profile`.`class_id` = 6
  AND `profile`.`spec_tag` = 'blood_death_knight'
  AND `profile`.`role` = 'tank'
  AND NOT EXISTS (
      SELECT 1 FROM `bot_rotation_action` AS `existing`
      WHERE `existing`.`profile_id` = `profile`.`id`
        AND `existing`.`spell_id` = 77575
  );

UPDATE `bot_rotation_profile`
SET `version` = CASE WHEN `version` < 29 THEN 29 ELSE `version` END,
    `source_note` = 'phase9_blood_outbreak_disease_upkeep_2026_09_23',
    `scope_note` = 'Maintain Blood Plague and Frost Fever with native Outbreak, keeping Icy Touch and Plague Strike as cooldown fallbacks'
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
--   AND `spell_id` = 77575
--   AND `sort_order` = 38
--   AND `mechanic_tags` = 'outbreak,diseases,blood_plague,frost_fever,maintain_owned_aura,no_rune_cost';
-- UPDATE `bot_rotation_profile`
-- SET `version` = 28,
--     `source_note` = 'phase9_blood_mangle_disease_runes_2026_09_23',
--     `scope_note` = 'Hold Heart Strike, Icy Touch and Plague Strike while the Magmaw Mangle seat aura 78412 is up so Death Strike gets the runes'
-- WHERE `class_id` = 6
--   AND `spec_tag` = 'blood_death_knight'
--   AND `role` = 'tank'
--   AND `source_note` = 'phase9_blood_outbreak_disease_upkeep_2026_09_23';
-- END REVERSE MIGRATION
