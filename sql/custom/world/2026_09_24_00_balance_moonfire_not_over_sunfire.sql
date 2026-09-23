-- Balance: do not overwrite a live Sunfire with the maintained Moonfire DoT
-- (DPS-066, part 3).
--
-- Evidence, Magmaw 10N Balance 30001, verdict b2-fd4ba456: when Solar Eclipse
-- ends, the maintained Moonfire `dot` row recasts Moonfire on Magmaw while the
-- Sunfire applied in Solar is still ticking. The recast replaces that Sunfire.
-- This wastes two GCDs per kill, about 0.3k DPS.
--   * The resolver's Eclipse gate is keyed on spell id. It rejects Moonfire
--     only during Solar Eclipse and Sunfire only outside it.
--   * The Moonfire row maintains aura 8921 with refresh_aura_below_ms = 3000.
--     After Solar ends the target carries Sunfire 93402, not Moonfire 8921, so
--     the maintain gate sees no Moonfire and admits a fresh cast.
--
-- Native facts from the pinned 4.3.4 DBC (Spell.dbc SHA-256
-- 088a14963d3f81a10963702c760215f49ff73132bea751306c57aae0dae9f39f,
-- SpellEffect.dbc SHA-256
-- e3d9a470bbcb5cea4e3f2947911a908b816cc60e6ffeb9f70b4cfb123bad6252,
-- SpellDuration.dbc SHA-256
-- 284e22a843ce4cb85604cd037d228f55a757ea3a608e59e3a5f30cbba02bc727):
--   * Moonfire 8921 and Sunfire 93402 both have effect 0 APPLY_AURA (6) with
--     PERIODIC_DAMAGE (3), a 2000 ms period, and effect 1 SCHOOL_DAMAGE (2).
--     Both use DurationIndex 29 (12 s) and RangeIndex 5 (40 yd). The target
--     aura id of a live Sunfire is therefore 93402.
--   * World DB spell_group 1123 holds 8921 and 93402 with stack rule 2
--     (SPELL_GROUP_STACK_RULE_EXCLUSIVE_FROM_SAME_CASTER). A druid's Moonfire
--     replaces that druid's own live Sunfire.
--
-- Change: forbidden_target_aura = 93402 on the Balance DPS profile's Moonfire
-- `dot` row only. That plain target-aura gate ("forbidden_target_aura_active"
-- in the candidate builder, "forbidden_target_aura" in the resolver) holds the
-- row while Sunfire is live. Once Sunfire expires, the unchanged maintain gate
-- recasts Moonfire. forbidden_owned_target_aura is deliberately not used,
-- because a non-zero value disables the maintain/refresh branch of the row.
-- The gate is any-caster; only a Balance druid in Solar Eclipse can apply
-- Sunfire.
--
-- Unchanged: the Sunfire `dot` row on Solar entry, the moving-only Moonfire and
-- Sunfire `builder` rows from 2026_09_23_20 (requires_moving = 1), the
-- Restoration healer Moonfire row, and every weight, bucket, range, resource,
-- Eclipse, proc or native spell value. No cast is forced.
--
-- The migration is idempotent: the forbidden_target_aura = 0 guard makes a
-- second run a no-op. The changed row gets the tag
-- moonfire_not_over_sunfire_20260924 so the reverse migration is exact. The
-- reverse migration is a commented block at the end of this file, not a
-- separate file: the worldserver auto-updater applies every file in
-- sql/custom/world at startup, so a separate revert file would undo this one
-- immediately.

UPDATE `bot_rotation_action`
SET `forbidden_target_aura` = 93402,
    `mechanic_tags` = CONCAT(`mechanic_tags`, ',moonfire_not_over_sunfire_20260924')
WHERE `profile_id` IN (
    SELECT `id`
    FROM `bot_rotation_profile`
    WHERE `class_id` = 11
      AND `spec_tag` = 'balance_druid'
      AND `role` = 'dps'
      AND `enabled` = 1
  )
  AND `spell_id` = 8921
  AND `category` = 'dot'
  AND `requires_moving` = 0
  AND `forbidden_target_aura` = 0;

-- BEGIN REVERSE MIGRATION
-- UPDATE `bot_rotation_action`
-- SET `forbidden_target_aura` = 0,
--     `mechanic_tags` = REPLACE(`mechanic_tags`, ',moonfire_not_over_sunfire_20260924', '')
-- WHERE `profile_id` IN (
--     SELECT `id`
--     FROM `bot_rotation_profile`
--     WHERE `class_id` = 11
--       AND `spec_tag` = 'balance_druid'
--       AND `role` = 'dps'
--       AND `enabled` = 1
--   )
--   AND `spell_id` = 8921
--   AND `category` = 'dot'
--   AND `forbidden_target_aura` = 93402
--   AND `mechanic_tags` LIKE '%,moonfire_not_over_sunfire_20260924%';
-- END REVERSE MIGRATION
