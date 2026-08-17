-- Phase 8 melee class/APL alignment.
--
-- The values below are executable profile gates, not damage tuning.  They
-- preserve the native spell pipeline while removing actions that the pinned
-- Cataclysm APL deliberately makes unavailable in the corresponding state.
-- Pinned policy identities:
--   WoWSims provider revision 70d87383a9b92f30fb9e370c4676d3ce33b6e6b6
--   Arms  APL sha256 9fbce00181b66b79cc305264bd38bd4b0d8ab83089b4002c14eae98dadcd288c
--   Fury  APL sha256 8a4f711ca6c1165dca340488c44f9b87f33f833932bfdc2b24cc6d46a971b65f
--   Ret   APL sha256 6a92bb6d87a28ce394c9a2f4038eca04977400a0f8f39de066e04c754dc5f7f0

-- Arms: the pinned APL only enables Bladestorm when numberTargets > 1.
UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`min_enemies` = 2
WHERE p.`class_id` = 1
  AND p.`spec_tag` = 'arms_warrior'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 46924;

-- Arms: Overpower is selected by the pinned APL only while Taste for Blood
-- (60503) is active.  Keep native dodge/aura-state checks intact as well.
UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`required_self_aura` = 60503
WHERE p.`class_id` = 1
  AND p.`spec_tag` = 'arms_warrior'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 7384;

-- Fury: WoWSims' Inner Rage branch is currentRage >= 75, not 45 percent.
UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`min_primary_power_pct` = 0.75
WHERE p.`class_id` = 1
  AND p.`spec_tag` = 'fury_warrior'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 1134;

-- Fury: Execute follows the opening cooldown/Colossus Smash branch and is
-- still ahead of Bloodthirst in the APL execute branch.  Bucket 1, sort 25
-- expresses that without allowing Execute to outrank bucket-0 cooldowns.
UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`priority_bucket` = 1,
    a.`sort_order` = 25
WHERE p.`class_id` = 1
  AND p.`spec_tag` = 'fury_warrior'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 5308;

-- Fury: Berserker Rage is the final fallback in the pinned APL, not an
-- unconditional bucket-0 GCD.  Keep it available when the ordinary profile
-- has no higher-priority action, while retaining its native cooldown/aura.
UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`priority_bucket` = 4,
    a.`sort_order` = 80
WHERE p.`class_id` = 1
  AND p.`spec_tag` = 'fury_warrior'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 18499;

-- Fury: the pinned APL only casts Slam while Bloodsurge (46916) is active.
-- The native spell remains responsible for its cast-time/resource semantics.
UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`required_self_aura` = 46916
WHERE p.`class_id` = 1
  AND p.`spec_tag` = 'fury_warrior'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 1464;

-- Retribution: at three Holy Power the APL spends Templar's Verdict before
-- returning to Crusader Strike.  The native resolver already gates Verdict
-- on Holy Power 3/Divine Purpose; move the spend into the cooldown bucket.
UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`priority_bucket` = 0
WHERE p.`class_id` = 2
  AND p.`spec_tag` = 'retribution_paladin'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 85256;

-- Retribution: Divine Storm is present in the pinned single-target/multi-
-- target APL only at numberTargets >= 4.
UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`min_enemies` = 4
WHERE p.`class_id` = 2
  AND p.`spec_tag` = 'retribution_paladin'
  AND p.`role` = 'dps'
  AND a.`spell_id` = 53385;

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 8),
    `source_note` = 'phase8_melee_apl_alignment_2026_08_17',
    `scope_note` = 'Pinned Arms, Fury, and Retribution APL state and priority alignment'
WHERE (`class_id` = 1 AND `spec_tag` IN ('arms_warrior', 'fury_warrior') AND `role` = 'dps')
   OR (`class_id` = 2 AND `spec_tag` = 'retribution_paladin' AND `role` = 'dps');
