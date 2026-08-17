-- Align the Shadow Priest burst sequence with the pinned WoWSims Cataclysm APL.
--
-- Evidence identity:
--   WoWSims source revision: 70d87383a9b92f30fb9e370c4676d3ce33b6e6b6
--   APL SHA256: 5899b39fdedfc369cafc3bb44b938eb22ab9964e71acd827178ce15812aac0b5
--   local debug trace: /tmp/wowsims-trace-baselines/results/shadow_priest.debug.result.json
--
-- priorityList[2] is the one-action "fiend" sequence:
--   auraNumStacks(87118) == 5 && spellIsReady(87153) -> cast 34433.
-- priorityList[3] is the one-action "archangel" sequence:
--   auraIsActive(34433) && gcdIsReady() -> cast 87153.
--
-- The native candidate builder already preflights each action's own
-- cooldown/GCD/range.  The profile schema cannot express the APL's
-- cross-spell spellIsReady(87153) leaf or sequence state, so this migration
-- adds the fiend aura predicate that is representable without manufacturing
-- casts or bypassing native outcomes.  The existing Archangel row remains
-- gated by live Dark Evangelism until Trinity evidence confirms that the
-- summon path exposes owner aura 34433 to the profile evaluator.

SET @shadow_profile := (
    SELECT `id`
    FROM `bot_rotation_profile`
    WHERE `class_id` = 5
      AND `spec_tag` = 'shadow_priest'
      AND `role` = 'dps'
    LIMIT 1
);

-- Do not summon Shadowfiend before Dark Evangelism reaches five stacks.
UPDATE `bot_rotation_action`
SET `required_self_aura` = 87118,
    `required_self_aura_stacks` = 5
WHERE `profile_id` = @shadow_profile
  AND `spell_id` = 34433
  AND `mechanic_tags` = 'shadowfiend,pet,burst';

-- The Archangel row is intentionally not rewritten here.  The pinned APL's
-- auraIsActive(34433) predicate needs a live Trinity aura receipt before it
-- can safely replace the existing 87118x5 gate; spell_pri_archangel also
-- consumes that live Evangelism aura when the native effect lands.
