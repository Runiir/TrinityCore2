-- Blood Death Knight tank priority repair from the immutable d495 combat
-- attempt.  Death Strike keeps its existing score and all native legality
-- gates; placing it in the Heart Strike bucket lets the existing score
-- comparator choose the higher-scoring valid action.
--
-- The profile and spell predicates are repeated in the subquery so this
-- forward migration is safe to replay on a database that already has the
-- repaired bucket.  Heart Strike and every other profile action are left
-- untouched.
UPDATE `bot_rotation_action`
SET `priority_bucket` = 1
WHERE `profile_id` IN (
    SELECT `id`
    FROM `bot_rotation_profile`
    WHERE `class_id` = 6
      AND `spec_tag` = 'blood_death_knight'
      AND `role` = 'tank'
  )
  AND `spell_id` = 49998
  AND `priority_bucket` = 2;

UPDATE `bot_rotation_profile`
SET `version` = CASE WHEN `version` < 25 THEN 25 ELSE `version` END,
    `source_note` = 'phase9_blood_death_strike_priority_2026_09_19',
    `scope_note` = 'Keep Death Strike and Heart Strike in the same bucket so the higher-scoring valid action wins'
WHERE `class_id` = 6
  AND `spec_tag` = 'blood_death_knight'
  AND `role` = 'tank';
