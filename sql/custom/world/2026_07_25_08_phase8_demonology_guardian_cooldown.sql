-- Phase 8 Demonology Warlock guardian cooldown.
--
-- The pinned Incinerate APL summons Doomguard during a proc window.  Keep the
-- native cooldown authoritative and expose the summon as an explicit profile
-- action so the live clone receives the same guardian contribution.

INSERT INTO `bot_rotation_action`
    (`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
     `damage_weight`, `survival_weight`, `priority_bucket`, `min_enemies`,
     `max_enemies`, `target_selector`, `movement_directive`,
     `auto_attack_mode`, `min_range`, `max_range`, `requires_ranged_range`)
SELECT `profile`.`id`, 15, 18540, 'offensive_cooldown',
       'summon_doomguard,guardian,pinned_apl',
       1.05, 0.00, 1, 1, 1, 'enemy', 'ranged', 'none', 5, 35, 1
FROM `bot_rotation_profile` AS `profile`
WHERE `profile`.`class_id` = 9
  AND `profile`.`spec_tag` = 'demonology_warlock'
  AND `profile`.`role` = 'dps'
  AND NOT EXISTS (
      SELECT 1
      FROM `bot_rotation_action` AS `existing`
      WHERE `existing`.`profile_id` = `profile`.`id`
        AND `existing`.`spell_id` = 18540
  );
