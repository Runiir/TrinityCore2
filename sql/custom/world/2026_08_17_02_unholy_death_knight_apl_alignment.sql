-- Unholy Death Knight pinned-APL alignment.
--
-- The pinned default.apl.json (70d87383a9b92f30fb9e370c4676d3ce33b6e6b6)
-- casts Outbreak without a rune-count predicate.  The native spell has no
-- rune spend, so a profile min_ready_runes=1 can suppress disease application
-- while all runes are recovering.  Keep the APL policy declarative and let
-- the native spell cost check remain authoritative.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`min_ready_runes` = 0,
    `action`.`mechanic_tags` = 'outbreak,diseases,pinned_apl,no_rune_gate'
WHERE `profile`.`class_id` = 6
  AND `profile`.`spec_tag` = 'unholy_death_knight'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 77575;

-- WoWSims represents the Unholy ghoul as a persistent pet set up before the
-- scored window; Raise Dead does not appear in the Unholy combat priority.
-- The native setup path already submits and observes the learned Raise Dead
-- spell.  Keep the profile row for auditability/emergency recovery, but make
-- it ineligible while a pet exists so the combat resolver cannot spend a GCD
-- recasting or refreshing the persistent ghoul.  If the pet disappears, the
-- native persistent-setup path remains the source of truth for recovery.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`forbids_pet` = 1,
    `action`.`mechanic_tags` = 'raise_dead,permanent_ghoul,persistent_setup_only'
WHERE `profile`.`class_id` = 6
  AND `profile`.`spec_tag` = 'unholy_death_knight'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 46584;
