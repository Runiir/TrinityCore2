-- Assassination Rogue: Vendetta keeps its melee hold without a 5 yd
-- centre-distance cap (round 3).
--
-- Evidence, Magmaw 10N round 2 (2026-09-25): Vendetta 79140 was rejected
-- max_range_exceeded 1,691 times (smoke) and 1,831 times (r02-b1), exactly as
-- often as Mutilate 1329, while the rogue auto-attacked Magmaw at 6.4-8.6 yd
-- from its centre. No Vendetta was cast in any shard.
--
-- Cause: the assassination row carries requires_melee_range = 1 and
-- max_range = 5. Vendetta is a 30 yd spell (SpellRange 4, no melee flag), so
-- the resolver's nominal-melee-reach rule (BotWorldPopulationMgrCombatResolver
-- .cpp effectiveSpellMaxRange, round 3) does not apply to it: the explicit
-- 5 yd cap is intersected with the native envelope and compared with the
-- centre distance, which exceeds 5 yd on every large boss.
--
-- Change: Vendetta's max_range 5 -> 0. An unset maximum falls back to the
-- spell's native 30 yd range, and requires_melee_range = 1 (IsWithinMeleeRange,
-- native combat reach) still holds it to melee, as the rotation intends.
-- Unchanged: the cooldown group, bucket, weights, the raid offensive-cooldown
-- reservation, and every other row. Mutilate, Envenom, Rupture and Kick are
-- SPELL_RANGE_MELEE and are covered by the resolver rule. The changed row gets
-- the tag vendetta_native_range_20260926 so the reverse migration is exact.

UPDATE `bot_rotation_action`
SET `max_range` = 0,
    `mechanic_tags` = CONCAT(`mechanic_tags`, ',vendetta_native_range_20260926')
WHERE `profile_id` IN (
    SELECT `id`
    FROM `bot_rotation_profile`
    WHERE `class_id` = 4
      AND `spec_tag` = 'assassination_rogue'
      AND `role` = 'dps'
  )
  AND `spell_id` = 79140
  AND `requires_melee_range` = 1
  AND `max_range` = 5;

-- BEGIN REVERSE MIGRATION
-- UPDATE `bot_rotation_action`
-- SET `max_range` = 5,
--     `mechanic_tags` = REPLACE(`mechanic_tags`, ',vendetta_native_range_20260926', '')
-- WHERE `profile_id` IN (
--     SELECT `id`
--     FROM `bot_rotation_profile`
--     WHERE `class_id` = 4
--       AND `spec_tag` = 'assassination_rogue'
--       AND `role` = 'dps'
--   )
--   AND `spell_id` = 79140
--   AND `mechanic_tags` LIKE '%,vendetta_native_range_20260926%';
-- END REVERSE MIGRATION
