-- Phase 8 Frost Death Knight Masterfrost core-action tuning.
--
-- The provisioned Cataclysm target does not know Unholy Presence, so restore
-- Frost Presence. Add the pinned Masterfrost APL's core disease, pet cooldown,
-- and rune-reset actions. Empower Rune Weapon remains a low-priority fallback
-- so it is selected only after ordinary rune and runic-power attacks are gated.

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`spell_id` = 48266,
    `action`.`mechanic_tags` = 'frost_presence,self',
    `action`.`maintain_aura_id` = 48266
WHERE `profile`.`class_id` = 6
  AND `profile`.`spec_tag` = 'frost_death_knight'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 48265;

INSERT INTO `bot_rotation_action`
    (`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
     `damage_weight`, `survival_weight`, `priority_bucket`, `min_enemies`,
     `max_enemies`, `target_selector`, `movement_directive`, `auto_attack_mode`,
     `min_range`, `max_range`, `maintain_aura_id`, `forbidden_owned_target_aura`)
SELECT `profile`.`id`, 42, 46584, 'offensive_cooldown',
       'raise_dead,temporary_ghoul,masterfrost,burst',
       0.90, 0.10, 1, 1, 1, 'self', 'melee', 'melee', 0, 0, 0, 0
FROM `bot_rotation_profile` AS `profile`
WHERE `profile`.`class_id` = 6
  AND `profile`.`spec_tag` = 'frost_death_knight'
  AND `profile`.`role` = 'dps'
  AND NOT EXISTS (
      SELECT 1 FROM `bot_rotation_action` AS `existing`
      WHERE `existing`.`profile_id` = `profile`.`id`
        AND `existing`.`spell_id` = 46584
  );

INSERT INTO `bot_rotation_action`
    (`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
     `damage_weight`, `survival_weight`, `priority_bucket`, `min_enemies`,
     `max_enemies`, `target_selector`, `movement_directive`, `auto_attack_mode`,
     `min_range`, `max_range`, `maintain_aura_id`, `forbidden_owned_target_aura`)
SELECT `profile`.`id`, 45, 77575, 'debuff',
       'outbreak,diseases,blood_plague,frost_fever,masterfrost',
       0.90, 0, 1, 1, 1, 'enemy', 'melee', 'melee', 0, 30, 55078, 55078
FROM `bot_rotation_profile` AS `profile`
WHERE `profile`.`class_id` = 6
  AND `profile`.`spec_tag` = 'frost_death_knight'
  AND `profile`.`role` = 'dps'
  AND NOT EXISTS (
      SELECT 1 FROM `bot_rotation_action` AS `existing`
      WHERE `existing`.`profile_id` = `profile`.`id`
        AND `existing`.`spell_id` = 77575
  );

INSERT INTO `bot_rotation_action`
    (`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
     `damage_weight`, `survival_weight`, `priority_bucket`, `min_enemies`,
     `max_enemies`, `target_selector`, `movement_directive`, `auto_attack_mode`,
     `min_range`, `max_range`, `maintain_aura_id`, `forbidden_owned_target_aura`)
SELECT `profile`.`id`, 90, 47568, 'resource_generator',
       'empower_rune_weapon,rune_reset,runic_power,masterfrost,fallback',
       0.88, 0, 4, 1, 1, 'self', 'melee', 'melee', 0, 0, 0, 0
FROM `bot_rotation_profile` AS `profile`
WHERE `profile`.`class_id` = 6
  AND `profile`.`spec_tag` = 'frost_death_knight'
  AND `profile`.`role` = 'dps'
  AND NOT EXISTS (
      SELECT 1 FROM `bot_rotation_action` AS `existing`
      WHERE `existing`.`profile_id` = `profile`.`id`
        AND `existing`.`spell_id` = 47568
  );
