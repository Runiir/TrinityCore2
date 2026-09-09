-- Rune Strike is a native melee attack, not a five-yard center-distance action.
-- Spell56815 uses SpellRange2: raw5 yards, SPELL_RANGE_MELEE; the core applies
-- caster/target combat reach. The original July20 role profile encoded both
-- requires_melee_range=1 and max_range=5 for the ordinary Blood power dump.
-- An unset action cap now inherits the native melee envelope in the resolver.
UPDATE `bot_rotation_action`
SET `max_range` = 0
WHERE `profile_id` IN (
    SELECT `id` FROM `bot_rotation_profile`
    WHERE `class_id` = 6
      AND `spec_tag` = 'blood_death_knight'
      AND `role` = 'tank'
  )
  AND `spell_id` = 56815
  AND `requires_melee_range` = 1
  AND `max_range` = 5;
