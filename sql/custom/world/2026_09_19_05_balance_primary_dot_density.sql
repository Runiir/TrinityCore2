-- Balance primary DoTs must remain eligible on their native primary target
-- during movement.  The resolver still owns target legality, LOS, range,
-- aura refresh, cooldown, Eclipse, resource, and allow_multidot decisions.
--
-- Only the two rows observed rejected by max_enemies are changed.  The
-- predicate makes replay convergent and leaves already-unlimited rows alone.
UPDATE `bot_rotation_action`
SET `max_enemies` = 0
WHERE `profile_id` IN (
    SELECT `id`
    FROM `bot_rotation_profile`
    WHERE `class_id` = 11
      AND `spec_tag` = 'balance_druid'
      AND `role` = 'dps'
  )
  AND `spell_id` IN (8921, 5570)
  AND `max_enemies` = 1;

UPDATE `bot_rotation_profile`
SET `version` = CASE WHEN `version` < 3 THEN 3 ELSE `version` END,
    `source_note` = 'balance_druid_primary_dot_density_2026_09_19',
    `scope_note` = 'Primary Moonfire and Insect Swarm ignore density caps; native target, LOS, aura, cooldown, Eclipse, resource, and allow_multidot gates remain authoritative'
WHERE `class_id` = 11
  AND `spec_tag` = 'balance_druid'
  AND `role` = 'dps';
