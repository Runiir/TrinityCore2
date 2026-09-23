-- Balance moving filler: fill otherwise-idle movement with the native instant
-- Moonfire/Sunfire direct hit.
--
-- Evidence (base-0891a99 kills 1-3, actor 30001): Balance deals damage only
-- from stationary cast-time fillers. While it moves (about 10-13 s per kill,
-- mostly the Magmaw pincer approach and return legs), Wrath, Starfire and
-- Starsurge are rejected with movement_requires_instant_action and the
-- maintained DoT rows are rejected with maintain_aura_active, so the bot
-- often records no_valid_profile_action. Only one to three instants landed in
-- those windows.
--
-- The rows are additive, last-choice and moving-only, following the live
-- Affliction moving Fel Flame row (2026_09_12_02). The stationary APL rows are
-- untouched. Native spellbook, GCD, mana, range, LOS and target legality still
-- gate the cast. The resolver's existing Eclipse gate keys on spell id: it
-- rejects Moonfire during Solar Eclipse and Sunfire outside it, so exactly one
-- of the two rows can be legal at a time. Category `builder` gives these rows
-- stable action ids distinct from the maintained `dot` rows for the same
-- spells. No aura, proc, Eclipse energy, resource or target is created.
INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
 `damage_weight`, `priority_bucket`, `min_enemies`, `max_enemies`,
 `target_selector`, `movement_directive`, `auto_attack_mode`,
 `min_range`, `max_range`, `requires_moving`)
SELECT `p`.`id`, 140, 8921, 'builder', 'moonfire,moving_filler_20260923',
       0.10, 14, 1, 0, 'enemy', 'ranged', 'none', 0, 35, 1
FROM `bot_rotation_profile` AS `p`
WHERE `p`.`class_id` = 11 AND `p`.`spec_tag` = 'balance_druid'
  AND `p`.`role` = 'dps' AND `p`.`enabled` = 1
  AND NOT EXISTS (
    SELECT 1 FROM `bot_rotation_action` AS `a`
    WHERE `a`.`profile_id` = `p`.`id`
      AND `a`.`spell_id` = 8921
      AND `a`.`mechanic_tags` = 'moonfire,moving_filler_20260923'
  );

INSERT INTO `bot_rotation_action`
(`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
 `damage_weight`, `priority_bucket`, `min_enemies`, `max_enemies`,
 `target_selector`, `movement_directive`, `auto_attack_mode`,
 `min_range`, `max_range`, `requires_moving`)
SELECT `p`.`id`, 141, 93402, 'builder', 'sunfire,moving_filler_20260923',
       0.10, 14, 1, 0, 'enemy', 'ranged', 'none', 0, 40, 1
FROM `bot_rotation_profile` AS `p`
WHERE `p`.`class_id` = 11 AND `p`.`spec_tag` = 'balance_druid'
  AND `p`.`role` = 'dps' AND `p`.`enabled` = 1
  AND NOT EXISTS (
    SELECT 1 FROM `bot_rotation_action` AS `a`
    WHERE `a`.`profile_id` = `p`.`id`
      AND `a`.`spell_id` = 93402
      AND `a`.`mechanic_tags` = 'sunfire,moving_filler_20260923'
  );
