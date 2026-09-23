-- Fire Mage: lift the stale 35-yard caps on Pyroblast!, Flame Orb and Scorch
-- to their native 40 yards (DPS-064, DPS-044).
--
-- Evidence, baseline r3-47cd175 kill k4 (source a5c0f72b5d), Magmaw 10N. Actor
-- 30006 is the fixed Lava Parasite baiter, the lowest-GUID fire mage.
--   * Between waves it holds the lane anchor at (-316.0, -64.0, 212.9). Its
--     exact 3D distance to Magmaw there is 35.043 yd. Every boss hit from
--     6.7 s to 30.6 s, 54.7 s to 75.1 s and 99.9 s to 106.7 s lands from
--     that point. The other lane anchor is 34.992 yd away.
--   * The resolver compares GetExactDist with min(profile cap, native max
--     plus both combat reaches). At 35.043 yd the 35-yard caps on Pyroblast!
--     92315, Flame Orb 82731 and Scorch 2948 reject those rows. Fireball,
--     Living Bomb and Combustion have 40-yard caps and still resolve. These
--     silent losses to Fireball never appear in candidate_rejections, which
--     are recorded only when a resolution has no valid action.
--   * Hot Streak 48108 was present from 14.3 s to 31.0 s. The Pyroblast!
--     row was recorded only as already_casting or global_cooldown there, and
--     those gates run after the required-self-aura gate. No Pyroblast! was
--     cast in that window. The actor's only two Pyroblast! casts, at 31.2 s and
--     53.5 s, and its only Flame Orb, at 32.2 s, came while it moved between
--     lanes, 30.0 to 31.6 yd from Magmaw.
--   * Both mages use the same profile. 30007 stands 15 yd from Magmaw and
--     casts Pyroblast! 10 times, against 2 for 30006. The
--     combustion_dot_window gate needs an owned Pyroblast DoT (92315 or
--     11366), so 30006 casts one weak Combustion at 56.6 s in k4 (227k,
--     against 808k for 30007) and none in k5.
--   * Damage, 30006 against 30007 in k4: Pyroblast! 155k vs 730k, Ignite 464k
--     vs 962k, Combustion 227k vs 808k. These three account for 1.65M of the
--     1.96M gap between the two actors. Outside the parasite waves the two
--     mages deal equal damage: 36.7k against 36.1k DPS.
--
-- Native facts from the pinned 4.3.4 DBC (Spell.dbc SHA-256
-- 088a14963d3f81a10963702c760215f49ff73132bea751306c57aae0dae9f39f,
-- SpellRange.dbc SHA-256
-- 46fc3e766ff03f621a7641e2e440886475714f1304721c41e1e767d15ba87efd):
--   * Pyroblast! 92315, Flame Orb 82731 and Scorch 2948 use RangeIndex 5,
--     which is 0 to 40 yd with range flags 0, the same as Fireball 133,
--     Living Bomb 44457 and Combustion 11129.
--   * Fire Blast 2136 uses RangeIndex 4 (30 yd). Blast Wave 11113,
--     Flamestrike 2120 and Counterspell 2139 are also native 40-yard spells,
--     but no evidence ties them to this gap, so they are unchanged here.
--
-- This follows the precedent of 2026_09_08_01_fire_native_range.sql (Fireball
-- and Living Bomb) and 2026_09_13_04_fire_combustion_native_range.sql
-- (DPS-052, Combustion). The profile cap stays intersected with the native
-- envelope, so native legality is never widened. The migration changes no
-- priority, weight, bucket, aura, proc, multiplier, resource or native spell
-- value, adds no forced cast and leaves min_range = 9 unchanged. It affects
-- only the matching rows of enabled Fire DPS profiles, including disabled
-- duplicate actions, as DPS-052 did.
--
-- The migration is idempotent: the max_range = 35 guard makes a second run a
-- no-op. Each changed row gets the tag fire_native_range_20260923 so the
-- reverse migration is exact. The reverse migration is a commented block at
-- the end of this file, not a separate file: the worldserver auto-updater
-- applies every file in sql/custom/world at startup, so a separate revert
-- file would undo this one immediately.

UPDATE `bot_rotation_action`
SET `max_range` = 40,
    `mechanic_tags` = CONCAT(`mechanic_tags`, ',fire_native_range_20260923')
WHERE `profile_id` IN (
    SELECT `id`
    FROM `bot_rotation_profile`
    WHERE `class_id` = 8
      AND `spec_tag` = 'fire'
      AND `role` = 'dps'
      AND `enabled` = 1
  )
  AND `spell_id` IN (92315, 82731, 2948)
  AND `max_range` = 35;

-- BEGIN REVERSE MIGRATION
-- UPDATE `bot_rotation_action`
-- SET `max_range` = 35,
--     `mechanic_tags` = REPLACE(`mechanic_tags`, ',fire_native_range_20260923', '')
-- WHERE `profile_id` IN (
--     SELECT `id`
--     FROM `bot_rotation_profile`
--     WHERE `class_id` = 8
--       AND `spec_tag` = 'fire'
--       AND `role` = 'dps'
--       AND `enabled` = 1
--   )
--   AND `spell_id` IN (92315, 82731, 2948)
--   AND `max_range` = 40
--   AND `mechanic_tags` LIKE '%,fire_native_range_20260923%';
-- END REVERSE MIGRATION
