-- Phase 8 Shadow Priest calibration/runtime profile alignment.
-- Keep the live SQL profile authoritative while matching the pinned P4 APL's
-- required form and Dark Evangelism burst cycle.

SET @shadow_profile := (
    SELECT `id`
    FROM `bot_rotation_profile`
    WHERE `class_id` = 5
      AND `spec_tag` = 'shadow_priest'
      AND `role` = 'dps'
    LIMIT 1
);

DELETE FROM `bot_rotation_action`
WHERE `profile_id` = @shadow_profile
  AND `spell_id` IN (588, 15473, 26297, 34433, 79476, 87151, 87153);

DELETE FROM `bot_rotation_action`
WHERE `profile_id` = @shadow_profile
  AND ((`spell_id` = 32379
        AND `mechanic_tags` = 'shadow_word_death,masochism,mana')
    OR `spell_id` = 73510
    OR (`spell_id` = 8092
        AND `mechanic_tags` = 'mind_blast,shadowfiend,burst'));

INSERT INTO `bot_rotation_action`
    (`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
     `damage_weight`, `survival_weight`, `priority_bucket`, `min_enemies`, `max_enemies`,
     `required_self_aura`, `forbidden_self_aura`, `requires_ranged_range`,
     `target_selector`, `movement_directive`, `auto_attack_mode`, `min_range`, `max_range`,
     `maintain_aura_id`, `required_self_aura_stacks`, `cooldown_group`, `enabled`)
VALUES
    (@shadow_profile, 1, 15473, 'buff', 'shadowform,self,prepull_required',
     1.00, 0, 0, 1, 0,
     0, 15473, 0,
     'self', 'ranged', 'none', 0, 0,
     15473, 0, '', 1),
    (@shadow_profile, 2, 588, 'buff', 'inner_fire,self,prepull_required',
     0.95, 0, 0, 1, 0,
     0, 588, 0,
     'self', 'ranged', 'none', 0, 0,
     588, 0, '', 1),
    (@shadow_profile, 33, 79476, 'use_item', 'volcanic_potion,consumable,burst',
     1.00, 0, 1, 1, 0,
     0, 0, 0,
     'self', 'ranged', 'none', 0, 0,
     0, 0, '', 1),
    (@shadow_profile, 34, 26297, 'offensive_cooldown', 'berserking,racial,burst',
     1.00, 0, 1, 1, 0,
     0, 26297, 0,
     'self', 'ranged', 'none', 0, 0,
     0, 0, '', 1),
    (@shadow_profile, 35, 34433, 'offensive_cooldown', 'shadowfiend,pet,burst',
     1.00, 0, 1, 1, 0,
     0, 0, 1,
     'enemy', 'ranged', 'none', 5, 35,
     0, 0, '', 1),
    (@shadow_profile, 37, 87153, 'offensive_cooldown', 'dark_archangel,dark_evangelism,burst',
     1.00, 0, 1, 1, 0,
     87118, 0, 0,
     'self', 'ranged', 'none', 0, 0,
     0, 5, '', 1);

-- The densest-target calibration anchor lets Mind Sear reach the real eight-target
-- cluster. Direct spells and DoTs remain single-target-only so they do not consume
-- more mana and GCD time than the AoE channel they would displace.
UPDATE `bot_rotation_action`
SET `max_enemies` = 1
WHERE `profile_id` = @shadow_profile
  AND `spell_id` IN (8092, 32379);

-- The temporary r67 experiment required a Shadow Orb for every Mind Blast and
-- materially regressed the live rotation. Restore the catalog's ungated filler
-- while still allowing naturally available Orbs to be consumed.
UPDATE `bot_rotation_action`
SET `required_self_aura` = 0
WHERE `profile_id` = @shadow_profile
  AND `spell_id` = 8092
  AND `mechanic_tags` = 'mind_blast,orb_spender';

UPDATE `bot_rotation_action`
SET `max_enemies` = 1,
    `forbids_pet` = 0
WHERE `profile_id` = @shadow_profile
  AND `spell_id` IN (589, 2944, 34914);

-- Keep the DoTs through their final tick. Early refresh windows spent more
-- globals than they recovered in the live 300-second profile; Shadow Word: Pain
-- remains maintained by Mind Flay without a separate refresh cast.
UPDATE `bot_rotation_action`
SET `refresh_aura_below_ms` = 0
WHERE `profile_id` = @shadow_profile
  AND `spell_id` IN (2944, 34914);

-- Execute Shadow Word: Death before the generic Mind Blast filler, matching the
-- pinned APL and preserving its Masochism mana return during the final minute.
UPDATE `bot_rotation_action`
SET `sort_order` = 39
WHERE `profile_id` = @shadow_profile
  AND `spell_id` = 32379
  AND `mechanic_tags` = 'shadow_word_death,execute';

-- TrinityCore's live mana cadence needs both available recovery windows even
-- though the simulator APL disables Dispersion. Enter at 20% so 100 ms reaction
-- scheduling cannot spend a material fraction of the window below the hard gate.
UPDATE `bot_rotation_action`
SET `enabled` = 1,
    `max_self_health_pct` = 1.00,
    `max_mana_pct` = 0.20,
    `max_enemies` = 0,
    `forbidden_self_aura` = 0,
    `priority_bucket` = 3
WHERE `profile_id` = @shadow_profile
  AND `spell_id` = 47585;
