-- Phase 8 Frost Death Knight Army of the Dead cooldown.
--
-- The pinned Masterfrost APL casts Army of the Dead before combat. The live
-- calibration profile has no pre-pull action queue, so retain it as a high-value
-- one-target class cooldown ahead of the ordinary rune/runic-power cycle.

INSERT INTO `bot_rotation_action`
    (`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
     `damage_weight`, `survival_weight`, `priority_bucket`, `min_enemies`,
     `max_enemies`, `target_selector`, `movement_directive`, `auto_attack_mode`,
     `min_range`, `max_range`, `maintain_aura_id`, `forbidden_owned_target_aura`)
SELECT `profile`.`id`, 38, 42650, 'offensive_cooldown',
       'army_of_the_dead,temporary_ghouls,masterfrost,class_cooldown,prepull',
       1.00, 0.10, 1, 1, 1, 'self', 'melee', 'melee', 0, 0, 0, 0
FROM `bot_rotation_profile` AS `profile`
WHERE `profile`.`class_id` = 6
  AND `profile`.`spec_tag` = 'frost_death_knight'
  AND `profile`.`role` = 'dps'
  AND NOT EXISTS (
      SELECT 1 FROM `bot_rotation_action` AS `existing`
      WHERE `existing`.`profile_id` = `profile`.`id`
        AND `existing`.`spell_id` = 42650
  );
