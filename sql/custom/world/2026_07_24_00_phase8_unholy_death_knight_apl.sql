-- Phase 8 Unholy Death Knight pinned-APL recovery.
--
-- Tuning109 attempt 34 exposed two independent gaps: the live profile reached
-- only 57.74% of the hard reference and never completed its declared offensive
-- cooldown group. Restore the pinned APL's Unholy Presence, Army of the Dead,
-- Unholy Frenzy, Summon Gargoyle, Empower Rune Weapon, Blood Tap, and AoE Death
-- and Decay actions. Permit the existing rune/runic-power cycle at any enemy
-- count so the eight-target mode does not collapse to a partial profile.

INSERT INTO `bot_rotation_action`
    (`profile_id`, `sort_order`, `spell_id`, `category`, `mechanic_tags`,
     `damage_weight`, `survival_weight`, `priority_bucket`, `min_enemies`,
     `max_enemies`, `target_selector`, `movement_directive`, `auto_attack_mode`,
     `min_range`, `max_range`, `maintain_aura_id`, `min_ready_runes`,
     `requires_ground_target`)
SELECT `profile`.`id`, `action`.`sort_order`, `action`.`spell_id`,
       `action`.`category`, `action`.`mechanic_tags`, `action`.`damage_weight`,
       `action`.`survival_weight`, `action`.`priority_bucket`,
       `action`.`min_enemies`, `action`.`max_enemies`, `action`.`target_selector`,
       `action`.`movement_directive`, `action`.`auto_attack_mode`,
       `action`.`min_range`, `action`.`max_range`, `action`.`maintain_aura_id`,
       `action`.`min_ready_runes`, `action`.`requires_ground_target`
FROM `bot_rotation_profile` AS `profile`
JOIN (
    SELECT 15 AS `sort_order`, 48265 AS `spell_id`, 'buff' AS `category`,
           'unholy_presence,pinned_apl,persistent_combat_buff' AS `mechanic_tags`,
           0.60 AS `damage_weight`, 0.05 AS `survival_weight`,
           0 AS `priority_bucket`, 1 AS `min_enemies`, 0 AS `max_enemies`,
           'self' AS `target_selector`, 'melee' AS `movement_directive`,
           'melee' AS `auto_attack_mode`, 0 AS `min_range`, 0 AS `max_range`,
           48265 AS `maintain_aura_id`, 0 AS `min_ready_runes`,
           0 AS `requires_ground_target`
    UNION ALL
    SELECT 25, 42650, 'offensive_cooldown',
           'army_of_the_dead,temporary_ghouls,pinned_apl,class_cooldown,prepull',
           1.00, 0.10, 1, 1, 0, 'self', 'melee', 'melee', 0, 0, 0, 0, 0
    UNION ALL
    SELECT 27, 49016, 'offensive_cooldown',
           'unholy_frenzy,haste,pinned_apl,class_cooldown',
           0.99, 0.00, 1, 1, 0, 'self', 'melee', 'melee', 0, 0, 49016, 0, 0
    UNION ALL
    SELECT 29, 49206, 'offensive_cooldown',
           'summon_gargoyle,guardian,pinned_apl,class_cooldown',
           0.98, 0.00, 1, 1, 0, 'enemy', 'melee', 'melee', 0, 30, 0, 0, 0
    UNION ALL
    SELECT 31, 47568, 'offensive_cooldown',
           'empower_rune_weapon,rune_reset,pinned_apl,class_cooldown',
           0.96, 0.00, 1, 1, 0, 'self', 'melee', 'melee', 0, 0, 0, 0, 0
    UNION ALL
    SELECT 75, 45529, 'resource_generator',
           'blood_tap,rune_refresh,pinned_apl,resource_recovery',
           0.72, 0.00, 3, 1, 0, 'self', 'melee', 'melee', 0, 0, 0, 0, 0
    UNION ALL
    SELECT 55, 43265, 'aoe',
           'death_and_decay,ground_aoe,pinned_apl,rune_spender',
           0.95, 0.00, 1, 2, 0, 'ground_enemy', 'melee', 'melee', 0, 30, 0, 1, 1
) AS `action`
WHERE `profile`.`class_id` = 6
  AND `profile`.`spec_tag` = 'unholy_death_knight'
  AND `profile`.`role` = 'dps'
  AND NOT EXISTS (
      SELECT 1 FROM `bot_rotation_action` AS `existing`
      WHERE `existing`.`profile_id` = `profile`.`id`
        AND `existing`.`spell_id` = `action`.`spell_id`
  );

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`max_enemies` = 0
WHERE `profile`.`class_id` = 6
  AND `profile`.`spec_tag` = 'unholy_death_knight'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` IN (
      42650, -- Army of the Dead
      43265, -- Death and Decay
      45529, -- Blood Tap
      46584, -- Raise Dead
      47541, -- Death Coil
      47568, -- Empower Rune Weapon
      48265, -- Unholy Presence
      49016, -- Unholy Frenzy
      49206, -- Summon Gargoyle
      55090, -- Scourge Strike
      57330, -- Horn of Winter
      63560, -- Dark Transformation
      77575, -- Outbreak
      85948  -- Festering Strike
  );

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`target_selector` = CASE `action`.`spell_id`
        WHEN 43265 THEN 'ground_enemy'
        WHEN 49206 THEN 'enemy'
        ELSE `action`.`target_selector`
    END
WHERE `profile`.`class_id` = 6
  AND `profile`.`spec_tag` = 'unholy_death_knight'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` IN (43265, 49206);

-- Open AoE windows with Death and Decay while the initial full rune set is
-- available. Keeping min_enemies = 2 leaves the single-target cycle unchanged.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`priority_bucket` = 0
WHERE `profile`.`class_id` = 6
  AND `profile`.`spec_tag` = 'unholy_death_knight'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 43265;

-- TrinityCore grants owner aura 93426 when the ghoul reaches five Shadow
-- Infusion stacks. Use it as the deterministic SQL-side ready gate; the native
-- Dark Transformation spell script remains authoritative for consuming stacks.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`required_self_aura` = 93426,
    `action`.`requires_pet` = 1
WHERE `profile`.`class_id` = 6
  AND `profile`.`spec_tag` = 'unholy_death_knight'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 63560;
