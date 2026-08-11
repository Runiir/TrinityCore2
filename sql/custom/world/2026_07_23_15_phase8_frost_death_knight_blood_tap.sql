-- Phase 8 Frost Death Knight Blood Tap fallback.
--
-- The pinned Masterfrost APL uses Blood Tap to recover a rune opportunity.
-- Keep it in the fallback bucket so ordinary diseases, Howling Blast,
-- Obliterate, Frost Strike, and cooldown actions retain runtime authority.

INSERT INTO `bot_rotation_action`
    (`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
     `damage_weight`, `survival_weight`, `priority_bucket`, `min_enemies`,
     `max_enemies`, `target_selector`, `movement_directive`, `auto_attack_mode`,
     `min_range`, `max_range`, `maintain_aura_id`, `forbidden_owned_target_aura`)
SELECT `profile`.`id`, 88, 45529, 'resource_generator',
       'blood_tap,rune_activation,death_rune,masterfrost,fallback',
       0.89, 0, 4, 1, 1, 'self', 'melee', 'melee', 0, 0, 0, 0
FROM `bot_rotation_profile` AS `profile`
WHERE `profile`.`class_id` = 6
  AND `profile`.`spec_tag` = 'frost_death_knight'
  AND `profile`.`role` = 'dps'
  AND NOT EXISTS (
      SELECT 1 FROM `bot_rotation_action` AS `existing`
      WHERE `existing`.`profile_id` = `profile`.`id`
        AND `existing`.`spell_id` = 45529
  );
