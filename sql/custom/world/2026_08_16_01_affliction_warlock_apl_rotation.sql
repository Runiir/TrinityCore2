-- Bring the Affliction runtime profile onto the same player-action envelope as
-- the pinned WoWSims APL.  These remain ordinary learned spells selected by
-- the generic profile predicates and submitted through BotActionExecutor.

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 3),
    `source_note` = 'wowsims_affliction_apl_player_actions_v1',
    `scope_note` = 'typed live-state approximation of pinned Affliction APL'
WHERE `class_id` = 9 AND `spec_tag` = 'affliction_warlock' AND `role` = 'dps';

DELETE a FROM `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
WHERE p.`class_id` = 9 AND p.`spec_tag` = 'affliction_warlock' AND p.`role` = 'dps';

INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
 `damage_weight`, `survival_weight`, `priority_bucket`, `min_enemies`,
 `max_enemies`, `min_target_health_pct`, `max_target_health_pct`,
 `required_self_aura`, `target_selector`, `movement_directive`,
 `auto_attack_mode`, `min_range`, `max_range`, `maintain_aura_id`,
 `refresh_aura_below_ms`, `min_mana_pct`, `max_mana_pct`,
 `required_owned_target_aura`) VALUES
-- Demon Soul: Felhunter is used on cooldown in the opening and execute windows.
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=9 AND `spec_tag`='affliction_warlock' AND `role`='dps'),
  10, 77801, 'offensive_cooldown', 'demon_soul,felhunter,apl_priority_0',
  1.00, 0.10, 1, 1, 0, 0.00, 1.00, 0, 'self', 'ranged', 'none', 0, 0, 0, 0, 0.00, 1.00, 0),
-- Soulburn followed by the ordinary Soul Fire cast while its aura is observed.
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=9 AND `spec_tag`='affliction_warlock' AND `role`='dps'),
  20, 74434, 'offensive_cooldown', 'soulburn,soul_shard,apl_priority_2',
  0.96, 0.05, 2, 1, 0, 0.00, 1.00, 0, 'self', 'ranged', 'none', 0, 0, 0, 0, 0.00, 1.00, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=9 AND `spec_tag`='affliction_warlock' AND `role`='dps'),
  21, 6353, 'spender', 'soul_fire,soulburn,apl_priority_1_12',
  0.98, 0.00, 2, 1, 1, 0.00, 1.00, 74434, 'enemy', 'ranged', 'none', 12, 35, 0, 0, 0.00, 1.00, 0),
-- Owned DoTs are refreshed from observable target-aura duration only.
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=9 AND `spec_tag`='affliction_warlock' AND `role`='dps'),
  30, 603, 'dot', 'bane_of_doom,dot,maintain_owned_aura,apl_priority_3',
  0.98, 0.00, 3, 1, 1, 0.00, 1.00, 0, 'enemy', 'ranged', 'none', 12, 35, 603, 0, 0.00, 1.00, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=9 AND `spec_tag`='affliction_warlock' AND `role`='dps'),
  40, 172, 'dot', 'corruption,dot,maintain_owned_aura,apl_priority_4',
  0.96, 0.00, 4, 1, 1, 0.00, 1.00, 0, 'enemy', 'ranged', 'none', 12, 35, 172, 0, 0.00, 1.00, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=9 AND `spec_tag`='affliction_warlock' AND `role`='dps'),
  50, 30108, 'dot', 'unstable_affliction,dot,maintain_owned_aura,apl_priority_5',
  1.00, 0.00, 5, 1, 1, 0.00, 1.00, 0, 'enemy', 'ranged', 'none', 12, 35, 30108, 4500, 0.00, 1.00, 0),
-- Haunt retains native cooldown/resource authority.
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=9 AND `spec_tag`='affliction_warlock' AND `role`='dps'),
  60, 48181, 'spender', 'haunt,primary,apl_priority_6',
  1.00, 0.00, 6, 1, 1, 0.00, 1.00, 0, 'enemy', 'ranged', 'none', 12, 35, 0, 0, 0.00, 1.00, 0),
-- Life Tap is a low-mana recovery action outside the damage priority chain.
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=9 AND `spec_tag`='affliction_warlock' AND `role`='dps'),
  70, 1454, 'resource_generator', 'life_tap,mana_recovery,apl_priority_7_14',
  0.10, 0.20, 7, 1, 0, 0.00, 1.00, 0, 'self', 'ranged', 'none', 0, 0, 0, 0, 0.00, 0.15, 0),
-- Drain Soul replaces the ordinary filler in the observed <=25% execute band.
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=9 AND `spec_tag`='affliction_warlock' AND `role`='dps'),
  80, 1120, 'execute', 'drain_soul,channel,execute_25,apl_priority_9',
  1.00, 0.00, 8, 1, 1, 0.00, 0.25, 0, 'enemy', 'ranged', 'none', 12, 35, 0, 0, 0.00, 1.00, 0),
-- Fel Flame is available only when the player actually owns its proc aura.
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=9 AND `spec_tag`='affliction_warlock' AND `role`='dps'),
  90, 77799, 'spender', 'fel_flame,proc,apl_priority_8',
  0.82, 0.00, 9, 1, 1, 0.00, 1.00, 89937, 'enemy', 'ranged', 'none', 12, 35, 0, 0, 0.00, 1.00, 0),
-- Shadowflame remains native-range limited; Shadow Bolt is the final filler.
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=9 AND `spec_tag`='affliction_warlock' AND `role`='dps'),
  100, 47897, 'spender', 'shadowflame,short_range,apl_priority_10',
  0.84, 0.00, 10, 1, 1, 0.00, 1.00, 0, 'enemy', 'ranged', 'none', 0, 15, 0, 0, 0.00, 1.00, 0),
((SELECT `id` FROM `bot_rotation_profile` WHERE `class_id`=9 AND `spec_tag`='affliction_warlock' AND `role`='dps'),
  130, 686, 'builder', 'shadow_bolt,filler,apl_priority_13',
  0.78, 0.00, 13, 1, 1, 0.00, 1.00, 0, 'enemy', 'ranged', 'none', 12, 35, 0, 0, 0.00, 1.00, 0);
