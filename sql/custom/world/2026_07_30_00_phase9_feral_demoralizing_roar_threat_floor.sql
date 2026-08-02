-- Phase 9 Feral Druid native swarm-pickup threat floor.
--
-- Rerun53 completed all 14 Stonecore nodes without deaths, but Feral retained
-- only 70.49% of identity-scoped hostiles and exposed the healer on 22.47% of
-- eligible samples. The bounded native Demoralizing Roar branch executed 25
-- times against nearby healer-owned followers, yet spell 99 had no spell_threat
-- row. Core therefore distributed only its SpellLevel value (15 total threat)
-- across as many as 60 affected followers.
--
-- Rerun54 proved that 150000 converted the cast into real ownership, but a
-- 19-follower wave still required approximately three applications. Rerun56
-- then proved that one persistent immutable follower survived exactly three
-- 450000 applications before changing ownership. Use that direct three-cast
-- equivalent as the single-cast floor. At the observed 60-target maximum this
-- contributes 22,500 base threat per follower before ordinary tank modifiers.
-- Preserve damage, routing, victim selection, hazard policy, and every
-- acceptance threshold.

SET @feral_tank_profile := (
    SELECT `id`
    FROM `bot_rotation_profile`
    WHERE `class_id` = 11
      AND `spec_tag` = 'feral_druid_tank'
      AND `role` = 'tank'
    LIMIT 1
);

INSERT INTO `spell_threat` (`entry`, `flatMod`, `pctMod`, `apPctMod`)
VALUES (99, 1350000, 1.0, 0.0)
ON DUPLICATE KEY UPDATE
    `flatMod` = VALUES(`flatMod`),
    `pctMod` = VALUES(`pctMod`),
    `apPctMod` = VALUES(`apPctMod`);

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 6),
    `source_note` = 'phase9_feral_demoralizing_roar_threat_floor_2026_07_30',
    `scope_note` = 'Use native ten-yard Demoralizing Roar with an evidence-derived 1350000 total flat threat floor for nearby healer-owned follower pickup'
WHERE `id` = @feral_tank_profile;
