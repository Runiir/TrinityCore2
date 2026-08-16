-- Frost Death Knight player-observed priority and setup alignment.
--
-- The pinned dual-wield Masterfrost reference enters Unholy Presence through
-- spell 48265, spends excess runic power, reacts to Killing Machine and Rime,
-- maintains the caster's own Blood Plague, and uses Horn of Winter only after
-- ordinary damage actions are unavailable.  These remain declarative action
-- candidates: runtime observes the typed predicates, arbitrates resources,
-- and submits only ordinary learned spells through the native executor.

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 11),
    `source_note` = 'wowsims_cata_masterfrost_player_observed_v1',
    `scope_note` = 'typed RP/rune/proc/disease priority; native Unholy Presence setup; no state manufacture'
WHERE `class_id` = 6
  AND `spec_tag` = 'frost_death_knight'
  AND `role` = 'dps';

-- The spell is part of the ordinary Death Knight creation spell set. Runtime
-- still fails closed when the loaded player does not actually know it.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`spell_id` = 48265,
    `action`.`mechanic_tags` = 'unholy_presence,self,masterfrost,persistent_setup,native_cast',
    `action`.`maintain_aura_id` = 48265,
    `action`.`refresh_aura_below_ms` = 0,
    `action`.`max_enemies` = 0
WHERE `profile`.`class_id` = 6
  AND `profile`.`spec_tag` = 'frost_death_knight'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` IN (48265, 48266);

-- Blood Plague is aura 55078.  Plague Strike is spell 45462; using the cast
-- spell as maintain_aura_id made the candidate reappear without observing the
-- real disease. Ownership keeps another DK's disease from satisfying the gate.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`priority_bucket` = 1,
    `action`.`sort_order` = CASE WHEN `action`.`spell_id` = 77575 THEN 45 ELSE 47 END,
    `action`.`mechanic_tags` = CASE
      WHEN `action`.`spell_id` = 77575
        THEN 'outbreak,diseases,blood_plague,frost_fever,masterfrost,maintain_owned_aura,player_observed'
      ELSE 'plague_strike,blood_plague,masterfrost,maintain_owned_aura,player_observed'
    END,
    `action`.`maintain_aura_id` = 55078,
    `action`.`refresh_aura_below_ms` = 3000,
    `action`.`required_owned_target_aura` = 0,
    `action`.`forbidden_owned_target_aura` = 0,
    `action`.`max_enemies` = 0
WHERE `profile`.`class_id` = 6
  AND `profile`.`spec_tag` = 'frost_death_knight'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` IN (45462, 77575);

-- Ordinary actions remain useful fallbacks.  The typed alternates below add
-- observed RP/proc priority without replacing this profile with a fixed script.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`priority_bucket` = 5,
    `action`.`sort_order` = 60,
    `action`.`mechanic_tags` = 'obliterate,runes,masterfrost,ordinary_cycle,player_observed',
    `action`.`required_self_aura` = 0,
    `action`.`forbidden_self_aura` = 0,
    `action`.`required_owned_target_aura` = 55078,
    `action`.`min_primary_power_pct` = 0,
    `action`.`max_primary_power_pct` = 0.70,
    `action`.`min_ready_runes` = 2,
    `action`.`max_enemies` = 0
WHERE `profile`.`class_id` = 6
  AND `profile`.`spec_tag` = 'frost_death_knight'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 49020
  AND `action`.`mechanic_tags` NOT LIKE '%player_observed_priority_v1%';

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`priority_bucket` = 6,
    `action`.`sort_order` = 70,
    `action`.`mechanic_tags` = 'howling_blast,frost_fever,masterfrost,single_target,ordinary_cycle,player_observed',
    `action`.`required_self_aura` = 0,
    `action`.`forbidden_self_aura` = 59052,
    `action`.`min_primary_power_pct` = 0,
    `action`.`max_primary_power_pct` = 0.80,
    `action`.`min_ready_runes` = 1,
    `action`.`min_enemies` = 1,
    `action`.`max_enemies` = 0
WHERE `profile`.`class_id` = 6
  AND `profile`.`spec_tag` = 'frost_death_knight'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 49184
  AND `action`.`mechanic_tags` NOT LIKE '%player_observed_priority_v1%';

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`priority_bucket` = 8,
    `action`.`sort_order` = 80,
    `action`.`mechanic_tags` = 'frost_strike,runic_power,masterfrost,ordinary_cycle,player_observed',
    `action`.`required_self_aura` = 0,
    `action`.`forbidden_self_aura` = 0,
    `action`.`min_primary_power_pct` = 0,
    `action`.`max_primary_power_pct` = 1,
    `action`.`min_ready_runes` = 0,
    `action`.`max_enemies` = 0
WHERE `profile`.`class_id` = 6
  AND `profile`.`spec_tag` = 'frost_death_knight'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 49143
  AND `action`.`mechanic_tags` NOT LIKE '%player_observed_priority_v1%';

-- Horn is a real no-target resource generator, not an aura-maintenance action.
-- Keeping it in the final bucket lets the player fill an otherwise idle GCD.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`category` = 'resource_generator',
    `action`.`priority_bucket` = 9,
    `action`.`sort_order` = 200,
    `action`.`mechanic_tags` = 'horn_of_winter,self,runic_power_filler,lowest_priority,player_observed',
    `action`.`maintain_aura_id` = 0,
    `action`.`refresh_aura_below_ms` = 0,
    `action`.`max_enemies` = 0
WHERE `profile`.`class_id` = 6
  AND `profile`.`spec_tag` = 'frost_death_knight'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 57330;

-- Rerunning the migration replaces only these authored alternatives.
DELETE `action` FROM `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
WHERE `profile`.`class_id` = 6
  AND `profile`.`spec_tag` = 'frost_death_knight'
  AND `profile`.`role` = 'dps'
  AND `action`.`mechanic_tags` LIKE '%player_observed_priority_v1%';

-- RP cap protection occurs before proc/rune actions in the pinned priority.
INSERT INTO `bot_rotation_action`
    (`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
     `damage_weight`, `priority_bucket`, `min_enemies`, `max_enemies`,
     `required_self_aura`, `target_selector`, `movement_directive`,
     `auto_attack_mode`, `min_range`, `max_range`, `min_primary_power_pct`,
     `max_primary_power_pct`, `min_ready_runes`)
SELECT `profile`.`id`, 52, 49143, 'spender',
       'frost_strike,runic_power,cap_protection,masterfrost,player_observed_priority_v1',
       1.06, 2, 1, 0, 0, 'enemy', 'melee', 'melee', 0, 5, 0.70, 1, 0
FROM `bot_rotation_profile` AS `profile`
WHERE `profile`.`class_id` = 6
  AND `profile`.`spec_tag` = 'frost_death_knight'
  AND `profile`.`role` = 'dps';

-- Killing Machine is an observed aura predicate; no proc is created or held.
INSERT INTO `bot_rotation_action`
    (`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
     `damage_weight`, `priority_bucket`, `min_enemies`, `max_enemies`,
     `required_self_aura`, `required_owned_target_aura`, `target_selector`,
     `movement_directive`, `auto_attack_mode`, `min_range`, `max_range`,
     `min_primary_power_pct`, `max_primary_power_pct`, `min_ready_runes`)
SELECT `profile`.`id`, 54, 49020, 'spender',
       'obliterate,killing_machine,runes,masterfrost,player_observed_priority_v1',
       1.04, 2, 1, 0, 51124, 55078, 'enemy', 'melee', 'melee', 0, 5, 0, 0.70, 2
FROM `bot_rotation_profile` AS `profile`
WHERE `profile`.`class_id` = 6
  AND `profile`.`spec_tag` = 'frost_death_knight'
  AND `profile`.`role` = 'dps';

-- Rime's native spell-cost modifier is applied by candidate and executor
-- preflight exactly as Spell::CheckRuneCost applies it. min_ready_runes=0 is
-- declarative observation of that free-cast envelope, not a rune mutation.
INSERT INTO `bot_rotation_action`
    (`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
     `damage_weight`, `priority_bucket`, `min_enemies`, `max_enemies`,
     `required_self_aura`, `target_selector`, `movement_directive`,
     `auto_attack_mode`, `min_range`, `max_range`, `min_primary_power_pct`,
     `max_primary_power_pct`, `min_ready_runes`)
SELECT `profile`.`id`, 56, 49184, 'spender',
       'howling_blast,rime,free_cast,masterfrost,player_observed_priority_v1',
       1.02, 2, 1, 0, 59052, 'enemy', 'melee', 'melee', 0, 30, 0, 0.90, 0
FROM `bot_rotation_profile` AS `profile`
WHERE `profile`.`class_id` = 6
  AND `profile`.`spec_tag` = 'frost_death_knight'
  AND `profile`.`role` = 'dps';
