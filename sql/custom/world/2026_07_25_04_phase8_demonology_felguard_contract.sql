-- Phase 8 Demonology Warlock Felguard contract.
--
-- The first representative campaign exposed a deterministic no-pet loop:
-- Demon Soul remained the highest-priority eligible action and failed with
-- SPELL_FAILED_NO_PET on every decision tick. Summon the pinned APL's Felguard
-- whenever no pet is active, and make Demon Soul explicitly pet-dependent.

INSERT INTO `bot_rotation_action`
    (`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
     `damage_weight`, `survival_weight`, `priority_bucket`, `min_enemies`,
     `max_enemies`, `target_selector`, `movement_directive`, `auto_attack_mode`,
     `min_range`, `max_range`, `forbids_pet`)
SELECT `profile`.`id`, 5, 30146, 'buff',
       'summon_felguard,felguard_pet,pinned_apl,persistent_setup',
       0.50, 0.10, 0, 1, 0, 'self', 'ranged', 'none', 0, 0, 1
FROM `bot_rotation_profile` AS `profile`
WHERE `profile`.`class_id` = 9
  AND `profile`.`spec_tag` = 'demonology_warlock'
  AND `profile`.`role` = 'dps'
  AND NOT EXISTS (
      SELECT 1
      FROM `bot_rotation_action` AS `existing`
      WHERE `existing`.`profile_id` = `profile`.`id`
        AND `existing`.`spell_id` = 30146
  );

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`requires_pet` = 1
WHERE `profile`.`class_id` = 9
  AND `profile`.`spec_tag` = 'demonology_warlock'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 77801;
