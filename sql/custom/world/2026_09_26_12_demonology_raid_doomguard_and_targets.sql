-- Demonology Warlock: native self-cast Doomguard and Shadowflame, and a
-- two-target ceiling for the single-target rotation (round 3).
--
-- Evidence, BWD 10N round 2 (r02-b1, 2026-09-25):
--   * Maloriak shard, warlock 11004010: every diagnose snapshot (16 of 16)
--     chose Summon Doomguard 18540 with reject reason out_of_range, although
--     Immolate, Corruption, Bane of Doom, Hand of Gul'dan and Incinerate were
--     VALID in 14 of them. Shadowflame 47897 was out_of_range in 16 of 16.
--   * Atramedes spirit pack, warlock 11003010: 264 trace attempts were
--     offensive_cooldown 18540 out_of_range; the route then logged
--     validation_route_target_search tactical_path_rejected (8x) and the
--     warlock waited in candidate backoff instead of casting. Bane of Doom,
--     Immolate, Hand of Gul'dan, Corruption and Soul Fire were
--     enemy_count_too_high in 11 of 11 snapshots.
--   * Magmaw b1 encounter: 18540 out_of_range 29 times.
--
-- Cause:
--   * Summon Doomguard 18540 and Shadowflame 47897 are native self-cast
--     spells (SpellRange 1, 0 yd). The Demonology rows target 'enemy', so the
--     candidate builder demands the warlock stand within 5 yd of the target's
--     hitbox (out_of_range), and the resolver's range-recovery path keeps the
--     bucket-0 Doomguard as the selected action ahead of every valid bucket-1
--     action, then asks the route to walk the caster into melee.
--     2026_09_13_02_affliction_doomguard.sql (DPS-053) and
--     2026_08_16_03_affliction_shadowflame_self_centered.sql already fixed the
--     same rows for Affliction.
--   * The Phase 1 coverage rows and the pinned-APL rows gave Immolate,
--     Corruption, Bane of Doom, Hand of Gul'dan, Soulburn and both Soul Fire
--     rows max_enemies = 1, so a boss with a single engaged add within 12 yd
--     reduced the warlock to Incinerate.
--
-- Change (profile demonology_warlock/dps only):
--   * Summon Doomguard 18540: target_selector 'self', min/max range 0,
--     requires_ranged_range 0, max_enemies 0 (the Affliction DPS-053 row).
--     It stays the bucket-0 opener; the raid cooldown reservation (tag
--     guardian) now holds it on trash and pre-pull and releases it in boss
--     combat, which the out_of_range rejection used to bypass.
--   * Shadowflame 47897: target_selector 'self' with its 8 yd hostile envelope
--     (the Affliction row). It is admitted when the warlock is within 8 yd of
--     the target and never pulls the caster in.
--   * Immolate 348, Corruption 172, Bane of Doom 603, Hand of Gul'dan 71521,
--     Soulburn 74434 and both Soul Fire 6353 rows: max_enemies 1 -> 2 (boss
--     plus one add). Three or more enemies keep the existing AoE rows
--     (Hellfire, Metamorphosis Incinerate) and the Incinerate filler.
-- Unchanged: Drain Life (its raid behaviour is the resolver's healer-owned
-- recovery gate), Life Tap, Metamorphosis, Demon Soul, the Felguard summon,
-- every weight, bucket and native spell value. The changed rows get the tag
-- demo_raid_targets_20260926 so the reverse migration is exact.

UPDATE `bot_rotation_action`
SET `target_selector` = 'self',
    `min_range` = 0,
    `max_range` = 0,
    `requires_ranged_range` = 0,
    `max_enemies` = 0,
    `mechanic_tags` = CONCAT(`mechanic_tags`, ',demo_raid_targets_20260926')
WHERE `profile_id` IN (
    SELECT `id`
    FROM `bot_rotation_profile`
    WHERE `class_id` = 9
      AND `spec_tag` = 'demonology_warlock'
      AND `role` = 'dps'
  )
  AND `spell_id` = 18540
  AND `target_selector` = 'enemy';

UPDATE `bot_rotation_action`
SET `target_selector` = 'self',
    `min_range` = 0,
    `max_range` = 8,
    `mechanic_tags` = CONCAT(`mechanic_tags`, ',demo_raid_targets_20260926')
WHERE `profile_id` IN (
    SELECT `id`
    FROM `bot_rotation_profile`
    WHERE `class_id` = 9
      AND `spec_tag` = 'demonology_warlock'
      AND `role` = 'dps'
  )
  AND `spell_id` = 47897
  AND `target_selector` = 'enemy';

UPDATE `bot_rotation_action`
SET `max_enemies` = 2,
    `mechanic_tags` = CONCAT(`mechanic_tags`, ',demo_raid_targets_20260926')
WHERE `profile_id` IN (
    SELECT `id`
    FROM `bot_rotation_profile`
    WHERE `class_id` = 9
      AND `spec_tag` = 'demonology_warlock'
      AND `role` = 'dps'
  )
  AND `spell_id` IN (348, 172, 603, 71521, 74434, 6353)
  AND `max_enemies` = 1;

-- BEGIN REVERSE MIGRATION
-- UPDATE `bot_rotation_action`
-- SET `target_selector` = 'enemy',
--     `min_range` = 5,
--     `max_range` = 18,
--     `requires_ranged_range` = 1,
--     `max_enemies` = 1,
--     `mechanic_tags` = REPLACE(`mechanic_tags`, ',demo_raid_targets_20260926', '')
-- WHERE `profile_id` IN (
--     SELECT `id`
--     FROM `bot_rotation_profile`
--     WHERE `class_id` = 9
--       AND `spec_tag` = 'demonology_warlock'
--       AND `role` = 'dps'
--   )
--   AND `spell_id` = 18540
--   AND `mechanic_tags` LIKE '%,demo_raid_targets_20260926%';
--
-- UPDATE `bot_rotation_action`
-- SET `target_selector` = 'enemy',
--     `mechanic_tags` = REPLACE(`mechanic_tags`, ',demo_raid_targets_20260926', '')
-- WHERE `profile_id` IN (
--     SELECT `id`
--     FROM `bot_rotation_profile`
--     WHERE `class_id` = 9
--       AND `spec_tag` = 'demonology_warlock'
--       AND `role` = 'dps'
--   )
--   AND `spell_id` = 47897
--   AND `mechanic_tags` LIKE '%,demo_raid_targets_20260926%';
--
-- UPDATE `bot_rotation_action`
-- SET `max_enemies` = 1,
--     `mechanic_tags` = REPLACE(`mechanic_tags`, ',demo_raid_targets_20260926', '')
-- WHERE `profile_id` IN (
--     SELECT `id`
--     FROM `bot_rotation_profile`
--     WHERE `class_id` = 9
--       AND `spec_tag` = 'demonology_warlock'
--       AND `role` = 'dps'
--   )
--   AND `spell_id` IN (348, 172, 603, 71521, 74434, 6353)
--   AND `mechanic_tags` LIKE '%,demo_raid_targets_20260926%';
-- END REVERSE MIGRATION
