-- Rogue APL alignment for the pinned Cataclysm references.
--
-- Keep this migration limited to executable profile predicates.  It does not
-- manufacture combo points, energy, poisons, or positional state; native spell
-- validation remains authoritative after the profile candidate is selected.

SET @assassination_profile := (
    SELECT `id`
    FROM `bot_rotation_profile`
    WHERE `class_id` = 4
      AND `spec_tag` = 'assassination_rogue'
      AND `role` = 'dps'
    LIMIT 1
);

SET @combat_profile := (
    SELECT `id`
    FROM `bot_rotation_profile`
    WHERE `class_id` = 4
      AND `spec_tag` = 'combat_rogue'
      AND `role` = 'dps'
    LIMIT 1
);

-- The pinned Assassination APL refreshes Rupture when the owned bleed is near
-- expiry.  The previous forbidden-owned-aura predicate made every active
-- Rupture reject before the maintain-aura path could run, so the bot only
-- reapplied it after the aura had fallen off.  Use the owner-scoped maintain
-- path and preserve the native target/aura ownership check.
UPDATE `bot_rotation_action`
SET `mechanic_tags` = 'rupture,owned_bleed,venomous_wounds,maintain_owned_aura',
    `forbidden_owned_target_aura` = 0,
    `maintain_aura_id` = 1943,
    `refresh_aura_below_ms` = 2000
WHERE `profile_id` = @assassination_profile
  AND `spell_id` = 1943;

-- Cold Blood is an explicit next-finisher cooldown in the pinned APL.  Require
-- the normal five-point branch instead of spending it on a low-point state;
-- the APL's final-five-seconds fallback is intentionally not synthesized by
-- this static profile schema.
UPDATE `bot_rotation_action`
SET `min_combo_points` = 5,
    `max_combo_points` = 5
WHERE `profile_id` = @assassination_profile
  AND `spell_id` = 14177;

-- The pinned Combat APL has no Rupture action.  Disable the legacy bleed row so
-- it cannot consume combo points/GCDs ahead of the APL's Eviscerate cycle.
UPDATE `bot_rotation_action`
SET `enabled` = 0
WHERE `profile_id` = @combat_profile
  AND `spell_id` = 1943;

-- WoWSims only uses Eviscerate at five combo points.  The old min=1 row relied
-- only on the native "has any combo point" check and therefore admitted
-- one-to-four-point finishers.
UPDATE `bot_rotation_action`
SET `min_combo_points` = 5,
    `max_combo_points` = 5
WHERE `profile_id` = @combat_profile
  AND `spell_id` = 2098;

-- Revealing Strike is only legal in the pinned APL while Slice and Dice has
-- more than five seconds remaining and combo points are at most four.  Keep
-- the existing owner-scoped debuff maintenance predicate and add the missing
-- self-aura/point gates.
UPDATE `bot_rotation_action`
SET `required_self_aura` = 5171,
    `min_self_aura_remaining_ms` = 5000,
    `max_combo_points` = 4
WHERE `profile_id` = @combat_profile
  AND `spell_id` = 84617;

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 10),
    `source_note` = 'phase9_rogue_apl_alignment_2026_08_17',
    `scope_note` = 'Pinned APL combo-point, Slice and Dice, owned-Rupture refresh, and Combat bleed gates'
WHERE `id` = @assassination_profile;

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 18),
    `source_note` = 'phase9_rogue_apl_alignment_2026_08_17',
    `scope_note` = 'Pinned Combat APL Eviscerate, Revealing Strike, and no-Rupture priority predicates'
WHERE `id` = @combat_profile;
