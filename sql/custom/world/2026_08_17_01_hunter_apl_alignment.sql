-- Hunter APL alignment for the pinned Cataclysm review.
--
-- Authority: WoWSims/cata revision
-- 70d87383a9b92f30fb9e370c4676d3ce33b6e6b6
--   marksmanship mm.apl.json
--     60aedd1aba0b508a4eedaf1a741fb568af1d508213804b1f675511b2c4f92ec6
--   survival sv.apl.json
--     66f2fa1560095697af336afdd7fa2c68d9f712bf96c76ade722a3270aa12f9ec
--
-- Keep this migration limited to typed profile predicates/order.  Native
-- SpellHistory, focus costs, target health, and spell execution remain the
-- authority; mechanic tags do not manufacture proc or cooldown state.

-- Marksmanship APL gates Serpent Sting behind the high-health E90 branch:
-- `not isExecutePhase(E90)` is true once the target is at or below 90%.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id` = `action`.`profile_id`
SET `action`.`max_target_health_pct` = 0.90,
    `action`.`mechanic_tags` = 'serpent_sting,dot,apl_not_e90'
WHERE `profile`.`class_id` = 3
  AND `profile`.`spec_tag` = 'marksmanship'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 1978;

-- Arcane Shot is the normal 66-focus-or-Chimera-cooldown branch.  The
-- profile has no time-to-ready predicate, so preserve the safe 66% focus
-- floor rather than spending focus below the APL's normal branch threshold.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id` = `action`.`profile_id`
SET `action`.`min_primary_power_pct` = 0.66,
    `action`.`mechanic_tags` = 'arcane_shot,focus_dump,apl_at_or_above_66_focus'
WHERE `profile`.`class_id` = 3
  AND `profile`.`spec_tag` = 'marksmanship'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 3044;

-- Chimera Shot is the normal below-E90 branch.  Native cooldown readiness is
-- still evaluated by SpellHistory; this health gate only mirrors the APL phase
-- boundary and prevents Chimera from consuming the high-health opener.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id` = `action`.`profile_id`
SET `action`.`max_target_health_pct` = 0.90,
    `action`.`mechanic_tags` = 'chimera_shot,focus,sting_refresh,apl_not_e90'
WHERE `profile`.`class_id` = 3
  AND `profile`.`spec_tag` = 'marksmanship'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 53209;

-- Aimed Shot is unconditional only in the APL's high-health E90 branch.  At
-- <=90% health it is legal only when the current cast is <=1 second.  The
-- two rows encode that OR without changing the native cast-time calculation.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id` = `action`.`profile_id`
SET `action`.`min_target_health_pct` = 0.90,
    `action`.`max_target_health_pct` = 1.00,
    `action`.`mechanic_tags` = 'aimed_shot,focus,apl_e90_or_fast_cast'
WHERE `profile`.`class_id` = 3
  AND `profile`.`spec_tag` = 'marksmanship'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 19434
  AND `action`.`sort_order` = 40;

DELETE `action` FROM `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id` = `action`.`profile_id`
WHERE `profile`.`class_id` = 3
  AND `profile`.`spec_tag` = 'marksmanship'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 19434
  AND `action`.`sort_order` = 41
  AND `action`.`mechanic_tags` = 'aimed_shot,focus,apl_fast_cast_below_e90';

INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
 `damage_weight`, `priority_bucket`, `min_enemies`, `max_target_health_pct`,
 `target_selector`, `movement_directive`, `auto_attack_mode`, `min_range`,
 `max_range`, `requires_stationary`, `max_cast_time_ms`)
VALUES
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 3 AND `spec_tag` = 'marksmanship' AND `role` = 'dps'),
 41, 19434, 'spender', 'aimed_shot,focus,apl_fast_cast_below_e90',
 0.92, 2, 1, 0.90, 'enemy', 'ranged', 'ranged', 10, 35, 1, 1000);

-- WoWSims' strict sequence is Chimera Shot followed by Readiness, and it is
-- only entered below E90.  A lower-damage same-bucket row lets Chimera win
-- while ready, then lets Readiness win over Serpent Sting on the following
-- decision so the native cooldown reset can occur.
DELETE `action` FROM `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id` = `action`.`profile_id`
WHERE `profile`.`class_id` = 3
  AND `profile`.`spec_tag` = 'marksmanship'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 23989
  AND `action`.`mechanic_tags` = 'readiness,apl_strict_sequence';

INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
 `damage_weight`, `priority_bucket`, `min_enemies`, `max_target_health_pct`,
 `target_selector`, `movement_directive`, `auto_attack_mode`)
VALUES
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 3 AND `spec_tag` = 'marksmanship' AND `role` = 'dps'),
 25, 23989, 'offensive_cooldown', 'readiness,apl_strict_sequence',
 0.95, 1, 1, 0.90, 'self', 'ranged', 'ranged');

-- Steady Focus is refreshed only when absent or within three seconds of
-- expiry.  Two mutually exclusive rows express the APL OR with typed aura
-- predicates while native cast time and resource checks remain authoritative.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id` = `action`.`profile_id`
SET `action`.`forbidden_self_aura` = 53221,
    `action`.`mechanic_tags` = 'steady_shot,focus_builder,apl_steady_focus_inactive'
WHERE `profile`.`class_id` = 3
  AND `profile`.`spec_tag` = 'marksmanship'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 56641
  AND `action`.`sort_order` = 70;

DELETE `action` FROM `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id` = `action`.`profile_id`
WHERE `profile`.`class_id` = 3
  AND `profile`.`spec_tag` = 'marksmanship'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 56641
  AND `action`.`sort_order` = 71
  AND `action`.`mechanic_tags` = 'steady_shot,focus_builder,apl_steady_focus_expiring';

INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
 `damage_weight`, `priority_bucket`, `min_enemies`, `target_selector`,
 `movement_directive`, `auto_attack_mode`, `min_range`, `max_range`,
 `requires_stationary`, `required_self_aura`, `max_self_aura_remaining_ms`)
VALUES
((SELECT `id` FROM `bot_rotation_profile`
  WHERE `class_id` = 3 AND `spec_tag` = 'marksmanship' AND `role` = 'dps'),
 71, 56641, 'resource_generator',
 'steady_shot,focus_builder,apl_steady_focus_expiring',
 0.74, 5, 1, 'enemy', 'ranged', 'ranged', 5, 35, 1, 53221, 3000);

-- The hidden Survival APL Multi Shot setup action is only used when this
-- hunter's Serpent Sting is absent.  Keep the existing multi-target gate and
-- add the ownership predicate so it does not repeat on every AOE decision.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id` = `action`.`profile_id`
SET `action`.`forbidden_owned_target_aura` = 1978,
    `action`.`mechanic_tags` = 'multi_shot,aoe,misdirection_transfer,apl_sting_missing'
WHERE `profile`.`class_id` = 3
  AND `profile`.`spec_tag` = 'survival'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 2643
  AND `action`.`sort_order` = 10;

-- Survival Kill Shot is above Black Arrow in the pinned APL.  Keep both in
-- the same bucket but retain Kill Shot's higher damage weight so the execute
-- action wins when both native cooldown and health gates are satisfied.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id` = `action`.`profile_id`
SET `action`.`priority_bucket` = 2,
    `action`.`mechanic_tags` = 'kill_shot,execute,after_explosive_shot,before_black_arrow'
WHERE `profile`.`class_id` = 3
  AND `profile`.`spec_tag` = 'survival'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 53351;

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 17),
    `source_note` = 'hunter_apl_alignment_2026_08_17',
    `scope_note` = 'Pinned MM APL phase/cast/focus/aura gates, Readiness sequence, and Survival Sting/execute ordering'
WHERE `class_id` = 3
  AND `spec_tag` IN ('marksmanship', 'survival')
  AND `role` = 'dps';
