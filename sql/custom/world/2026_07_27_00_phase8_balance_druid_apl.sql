-- Phase 8 Balance Druid pinned-APL alignment.
--
-- The first live Balance window after ranged-lane recovery remained on Starfire
-- for the full 300 seconds, never traversed Eclipse, omitted Moonkin Form and
-- Starfall from single-target use, and reached only 42.04% of the pinned P4
-- reference. The controller owns Eclipse direction and persistent form setup;
-- this SQL keeps the explicit runtime profile aligned with the remaining APL
-- actions and reference consumable.

SET @balance_profile := (
    SELECT `id`
    FROM `bot_rotation_profile`
    WHERE `class_id` = 11
      AND `spec_tag` = 'balance_druid'
      AND `role` = 'dps'
    LIMIT 1
);

DELETE FROM `bot_rotation_action`
WHERE `profile_id` = @balance_profile
  AND `spell_id` IN (29166, 79476, 88747, 88751, 93402);

INSERT INTO `bot_rotation_action`
    (`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
     `damage_weight`, `survival_weight`, `priority_bucket`, `min_enemies`,
     `max_enemies`, `target_selector`, `movement_directive`, `auto_attack_mode`,
     `min_range`, `max_range`, `maintain_aura_id`, `enabled`)
VALUES
    (@balance_profile, 5, 88747, 'offensive_cooldown',
     'wild_mushroom,prepull,pinned_apl',
     0.00, 0.00, 1, 1, 0, 'enemy', 'ranged', 'none', 0, 40, 0, 1),
    (@balance_profile, 15, 93402, 'dot',
     'sunfire,dot,solar_eclipse,pinned_apl',
     0.93, 0.00, 1, 1, 0, 'enemy', 'ranged', 'none', 0, 40, 93402, 1),
    (@balance_profile, 25, 79476, 'use_item',
     'volcanic_potion,consumable,pinned_apl',
     1.00, 0.00, 1, 1, 0, 'self', 'ranged', 'none', 0, 0, 0, 1),
    (@balance_profile, 28, 88751, 'offensive_cooldown',
     'wild_mushroom_detonate,solar_eclipse,pinned_apl',
     1.00, 0.00, 1, 1, 0, 'self', 'ranged', 'none', 0, 0, 0, 1);

-- The separate five-minute AoE fixture is much more mana-intensive than the
-- pinned single-target APL. Use Balance's real Innervate cooldown rather than
-- fixture-only mana injection so sustained Hurricane remains observable.
INSERT INTO `bot_rotation_action`
    (`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
     `damage_weight`, `survival_weight`, `priority_bucket`, `min_enemies`,
     `max_enemies`, `target_selector`, `movement_directive`, `auto_attack_mode`,
     `min_range`, `max_range`, `maintain_aura_id`, `max_mana_pct`, `enabled`)
VALUES
    (@balance_profile, 22, 29166, 'resource_generator',
     'innervate,mana_recovery,aoe_sustain',
     0.00, 1.20, 1, 3, 0, 'self', 'ranged', 'none', 0, 0, 0, 0.55, 1);

-- The pinned single-target APL allows Starfall as an ordinary cooldown. Its
-- original catalog row incorrectly restricted it to multi-target windows.
UPDATE `bot_rotation_action`
SET `sort_order` = 35,
    `priority_bucket` = 1,
    `min_enemies` = 1,
    `max_enemies` = 0,
    `mechanic_tags` = 'starfall,cooldown,pinned_apl'
WHERE `profile_id` = @balance_profile
  AND `spell_id` = 48505;

-- Fillers remain behind DoTs, Starsurge, potion, Starfall, and treants. The
-- controller's Eclipse-direction gate chooses exactly one of these two actions.
-- They remain available in AoE long enough to enter Solar before Hurricane.
UPDATE `bot_rotation_action`
SET `priority_bucket` = 3,
    `max_enemies` = 0,
    `requires_ranged_range` = 1,
    `min_range` = 5,
    `max_range` = 35
WHERE `profile_id` = @balance_profile
  AND `spell_id` IN (2912, 5176);
