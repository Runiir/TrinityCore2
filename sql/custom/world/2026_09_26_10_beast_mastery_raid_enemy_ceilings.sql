-- Beast Mastery Hunter: lift the Phase 1 coverage enemy ceilings that left
-- the raid hunter with no legal action on multi-target pulls (round 3).
--
-- Evidence, BWD 10N round 2 (r02-b1, 2026-09-25):
--   * Atramedes north spirit pack, hunter 11003003: 543 trace attempts ended
--     in profile_resolve no_valid_profile_action enemy_count_too_high and 207
--     in insufficient_resource; every diagnose snapshot (10 of 10) showed
--     Serpent Sting, Arcane Shot, Cobra Shot and Intimidation rejected as
--     enemy_count_too_high and Multi-Shot as insufficient_resource.
--   * Magmaw encounter (smoke and b1): Cobra Shot 77767 enemy_count_too_high
--     213 and 254 times, Arcane Shot 3044 112 and 236 times; hunter damage
--     uptime 0.49-0.51.
--
-- Cause: 2026_07_18_00_all_spec_rotation_profile_coverage.sql wrote every
-- single-target Beast Mastery row with max_enemies = 1 and Multi-Shot with
-- min_enemies = 3. The resolver counts the target plus every party-engaged
-- hostile within 12 yd of it, so with two engaged enemies nothing is legal,
-- and with three or more only Multi-Shot is. Its 40 focus drains in two casts
-- and the focus generator (Cobra Shot) is itself gated, so the hunter idles.
-- The profile was never refined after Phase 1 (Beast Mastery had no pinned
-- WoWSims source; the qualified hunter specs were Marksmanship/Survival).
--
-- Change (profile beast_mastery_hunter/dps only):
--   * Serpent Sting 1978, Kill Command 34026, Kill Shot 53351 and the focus
--     generator Cobra Shot 77767: max_enemies 1 -> 0 (no ceiling).
--   * Arcane Shot 3044: max_enemies 1 -> 2, so at three or more enemies the
--     focus dump is Multi-Shot (priority bucket 2 ahead of Arcane Shot's 3).
-- Unchanged: Multi-Shot's min_enemies = 3, Intimidation, every weight, bucket,
-- range, resource and native spell value. Single-target behaviour (one enemy)
-- is identical. The changed rows get the tag bm_raid_enemy_ceiling_20260926 so
-- the reverse migration is exact. The reverse migration is a commented block
-- at the end of this file: the worldserver auto-updater applies every file in
-- sql/custom/world at startup, so a separate revert file would undo this one.

UPDATE `bot_rotation_action`
SET `max_enemies` = 0,
    `mechanic_tags` = CONCAT(`mechanic_tags`, ',bm_raid_enemy_ceiling_20260926')
WHERE `profile_id` IN (
    SELECT `id`
    FROM `bot_rotation_profile`
    WHERE `class_id` = 3
      AND `spec_tag` = 'beast_mastery_hunter'
      AND `role` = 'dps'
  )
  AND `spell_id` IN (1978, 34026, 53351, 77767)
  AND `max_enemies` = 1;

UPDATE `bot_rotation_action`
SET `max_enemies` = 2,
    `mechanic_tags` = CONCAT(`mechanic_tags`, ',bm_raid_enemy_ceiling_20260926')
WHERE `profile_id` IN (
    SELECT `id`
    FROM `bot_rotation_profile`
    WHERE `class_id` = 3
      AND `spec_tag` = 'beast_mastery_hunter'
      AND `role` = 'dps'
  )
  AND `spell_id` = 3044
  AND `max_enemies` = 1;

-- BEGIN REVERSE MIGRATION
-- UPDATE `bot_rotation_action`
-- SET `max_enemies` = 1,
--     `mechanic_tags` = REPLACE(`mechanic_tags`, ',bm_raid_enemy_ceiling_20260926', '')
-- WHERE `profile_id` IN (
--     SELECT `id`
--     FROM `bot_rotation_profile`
--     WHERE `class_id` = 3
--       AND `spec_tag` = 'beast_mastery_hunter'
--       AND `role` = 'dps'
--   )
--   AND `spell_id` IN (1978, 3044, 34026, 53351, 77767)
--   AND `mechanic_tags` LIKE '%,bm_raid_enemy_ceiling_20260926%';
-- END REVERSE MIGRATION
