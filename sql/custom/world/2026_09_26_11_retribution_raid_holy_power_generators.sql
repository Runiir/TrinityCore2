-- Retribution Paladin: keep the Holy Power generator and the ordinary strikes
-- legal on multi-target raid pulls (round 3).
--
-- Evidence, BWD 10N round 2 (2026-09-25):
--   * Magmaw smoke encounter, paladin 11000006: Crusader Strike 35395
--     enemy_count_too_high 213 times (and max_range_exceeded 668 times, fixed
--     separately by the resolver's nominal-melee-reach rule), Judgement 163,
--     Exorcism 136, Templar's Verdict 53; Templar's Verdict and Inquisition
--     insufficient_holy_power 1,722 times each. No Crusader Strike, Templar's
--     Verdict or Inquisition damage in any shard.
--   * r02-b1 Atramedes spirit pack, paladin 11003006: all 11 diagnose snapshots
--     rejected Crusader Strike, Judgement, Exorcism and Hammer of Wrath as
--     enemy_count_too_high and Divine Storm as enemy_count_too_low; 1,389 of
--     1,408 trace attempts were melee_auto_attack_fallback. Its only damage was
--     Eye for an Eye (22,996, uptime 6.9%).
--
-- Cause: 2026_07_18_00_all_spec_rotation_profile_coverage.sql wrote Crusader
-- Strike, Templar's Verdict, Judgement, Exorcism and Hammer of Wrath with
-- max_enemies = 1; 2026_08_17_10_phase8_melee_apl_alignment.sql moved Divine
-- Storm to min_enemies = 4 (the pinned APL's numberTargets >= 4). With two or
-- three engaged enemies (the resolver counts the target plus party-engaged
-- hostiles within 12 yd of it) no Holy Power generator or strike was legal.
-- Divine Storm, when legal by count, was an 'enemy' row capped at 5 yd for a
-- zero-range self-centred spell (SpellRange 1): the resolver intersects that
-- with the combat-reach sum, so it rarely fit a normal-sized target either.
--
-- Change (profile retribution_paladin/dps only):
--   * Crusader Strike 35395, Templar's Verdict 85256, Judgement 20271,
--     Exorcism 879, Hammer of Wrath 24275: max_enemies 1 -> 0.
--   * Divine Storm 53385 (still min_enemies = 4): target_selector 'self' with
--     an 8 yd hostile envelope (its native radius), priority bucket 2 -> 1,
--     sort_order 70 -> 19 and damage_weight 0.90 -> 1.00. At four or more
--     enemies it now outranks Crusader Strike (bucket 1, 0.94), as the pinned
--     APL does; when an encounter forbids area damage or the target is out of
--     its radius, Crusader Strike still generates Holy Power. Templar's Verdict
--     (bucket 0) remains the spender at 3 Holy Power.
--   * Inquisition 84963: category offensive_cooldown -> buff. It has no
--     cooldown; it is the 3 Holy Power self buff (+30% Holy damage) that the
--     pinned APL keeps up. As an offensive cooldown the raid reservation held
--     it on every trash and pre-pull node (Maloriak shard: 14 of 16 diagnose
--     snapshots raid_offensive_cooldown_reserved), next to the real cooldowns
--     Avenging Wrath and Zealotry, which stay reserved.
-- Unchanged: single-target behaviour (one enemy), Rebuke, the seal, Avenging
-- Wrath and Zealotry rows, and Inquisition's bucket, order, weights and
-- maintain window. The changed rows get the tag ret_raid_holy_power_20260926
-- so the reverse migration is exact.

UPDATE `bot_rotation_action`
SET `max_enemies` = 0,
    `mechanic_tags` = CONCAT(`mechanic_tags`, ',ret_raid_holy_power_20260926')
WHERE `profile_id` IN (
    SELECT `id`
    FROM `bot_rotation_profile`
    WHERE `class_id` = 2
      AND `spec_tag` = 'retribution_paladin'
      AND `role` = 'dps'
  )
  AND `spell_id` IN (35395, 85256, 20271, 879, 24275)
  AND `max_enemies` = 1;

UPDATE `bot_rotation_action`
SET `target_selector` = 'self',
    `max_range` = 8,
    `priority_bucket` = 1,
    `sort_order` = 19,
    `damage_weight` = 1.00,
    `mechanic_tags` = CONCAT(`mechanic_tags`, ',ret_raid_holy_power_20260926')
WHERE `profile_id` IN (
    SELECT `id`
    FROM `bot_rotation_profile`
    WHERE `class_id` = 2
      AND `spec_tag` = 'retribution_paladin'
      AND `role` = 'dps'
  )
  AND `spell_id` = 53385
  AND `target_selector` = 'enemy';

UPDATE `bot_rotation_action`
SET `category` = 'buff',
    `mechanic_tags` = CONCAT(`mechanic_tags`, ',ret_raid_holy_power_20260926')
WHERE `profile_id` IN (
    SELECT `id`
    FROM `bot_rotation_profile`
    WHERE `class_id` = 2
      AND `spec_tag` = 'retribution_paladin'
      AND `role` = 'dps'
  )
  AND `spell_id` = 84963
  AND `category` = 'offensive_cooldown';

-- BEGIN REVERSE MIGRATION
-- UPDATE `bot_rotation_action`
-- SET `max_enemies` = 1,
--     `mechanic_tags` = REPLACE(`mechanic_tags`, ',ret_raid_holy_power_20260926', '')
-- WHERE `profile_id` IN (
--     SELECT `id`
--     FROM `bot_rotation_profile`
--     WHERE `class_id` = 2
--       AND `spec_tag` = 'retribution_paladin'
--       AND `role` = 'dps'
--   )
--   AND `spell_id` IN (35395, 85256, 20271, 879, 24275)
--   AND `mechanic_tags` LIKE '%,ret_raid_holy_power_20260926%';
--
-- UPDATE `bot_rotation_action`
-- SET `target_selector` = 'enemy',
--     `max_range` = 5,
--     `priority_bucket` = 2,
--     `sort_order` = 70,
--     `damage_weight` = 0.90,
--     `mechanic_tags` = REPLACE(`mechanic_tags`, ',ret_raid_holy_power_20260926', '')
-- WHERE `profile_id` IN (
--     SELECT `id`
--     FROM `bot_rotation_profile`
--     WHERE `class_id` = 2
--       AND `spec_tag` = 'retribution_paladin'
--       AND `role` = 'dps'
--   )
--   AND `spell_id` = 53385
--   AND `mechanic_tags` LIKE '%,ret_raid_holy_power_20260926%';
--
-- UPDATE `bot_rotation_action`
-- SET `category` = 'offensive_cooldown',
--     `mechanic_tags` = REPLACE(`mechanic_tags`, ',ret_raid_holy_power_20260926', '')
-- WHERE `profile_id` IN (
--     SELECT `id`
--     FROM `bot_rotation_profile`
--     WHERE `class_id` = 2
--       AND `spec_tag` = 'retribution_paladin'
--       AND `role` = 'dps'
--   )
--   AND `spell_id` = 84963
--   AND `mechanic_tags` LIKE '%,ret_raid_holy_power_20260926%';
-- END REVERSE MIGRATION
