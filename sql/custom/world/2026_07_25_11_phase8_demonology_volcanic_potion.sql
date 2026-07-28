-- Phase 8 Demonology Warlock Volcanic Potion contract.
--
-- The pinned Incinerate APL uses Volcanic Potion around its opening burst.
-- Execute the native item spell from deterministic inventory rather than
-- reproducing the potion's stat effect in the rotation profile.

INSERT INTO `bot_rotation_action`
    (`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
     `damage_weight`, `survival_weight`, `priority_bucket`, `min_enemies`,
     `max_enemies`, `target_selector`, `movement_directive`,
     `auto_attack_mode`, `maintain_aura_id`, `forbidden_self_aura`)
SELECT `profile`.`id`, 7, 79476, 'use_item',
       'volcanic_potion,prepot,pinned_apl',
       1.10, 0.00, 1, 1, 1, 'self', 'hold', 'none', 79476, 79476
FROM `bot_rotation_profile` AS `profile`
WHERE `profile`.`class_id` = 9
  AND `profile`.`spec_tag` = 'demonology_warlock'
  AND `profile`.`role` = 'dps'
  AND NOT EXISTS (
      SELECT 1
      FROM `bot_rotation_action` AS `existing`
      WHERE `existing`.`profile_id` = `profile`.`id`
        AND `existing`.`spell_id` = 79476
  );
