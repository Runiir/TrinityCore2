-- Phase 9 Arcane Mage multi-target route liveness.
--
-- The first strict Phase 9 Stonecore canary completed all 14 route nodes and
-- killed all four bosses, but Arcane Mage active-action coverage was 41.67%.
-- Immutable trace evidence showed 98 inactive profile resolutions. Arcane
-- Blast, Arcane Missiles, Arcane Barrage, Arcane Power, and Evocation were all
-- restricted to max_enemies=1, while Arcane Explosion required three enemies
-- within 10 yards. Two-target trash and ranged multi-target states therefore
-- had no legal explicit-profile action.

SET @arcane_profile := (
    SELECT `id`
    FROM `bot_rotation_profile`
    WHERE `class_id` = 8
      AND `spec_tag` = 'arcane_mage'
      AND `role` = 'dps'
    LIMIT 1
);

-- Keep the close-range Arcane Explosion branch separate, but allow the normal
-- ranged cycle, movement spender, burn cooldown, and mana recovery to remain
-- legal when more than one hostile is engaged.
UPDATE `bot_rotation_action`
SET `max_enemies` = 0
WHERE `profile_id` = @arcane_profile
  AND `spell_id` IN (12042, 30451, 5143, 44425, 12051);

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 3),
    `source_note` = 'phase9_arcane_multitarget_liveness_2026_07_28',
    `scope_note` = 'Preserve ranged Arcane actions across multi-target Stonecore route combat'
WHERE `id` = @arcane_profile;
