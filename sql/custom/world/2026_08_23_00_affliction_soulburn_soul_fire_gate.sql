-- Make the Affliction Soulburn window single-use for Soul Fire while keeping
-- both sides of the action pair bound to live player state. The native
-- Soulburn script consumes 74434 when 6353 lands; the profile gate below
-- requires a real Soul Shard for the preceding Soulburn candidate and the
-- live Soulburn aura for its Soul Fire spender.

UPDATE `bot_rotation_profile`
SET `version` = GREATEST(`version`, 4),
    `source_note` = 'wowsims_affliction_soulburn_window_v2',
    `scope_note` = 'typed live Soulburn/Soul Fire window with native one-use consumption'
WHERE `class_id` = 9
  AND `spec_tag` = 'affliction_warlock'
  AND `role` = 'dps';

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`mechanic_tags` = 'soulburn,soul_shard,live_resource,apl_priority_2'
WHERE `profile`.`class_id` = 9
  AND `profile`.`spec_tag` = 'affliction_warlock'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 74434;

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`mechanic_tags` = 'soul_fire,soulburn,live_aura,apl_priority_1_12',
    `action`.`required_self_aura` = 74434
WHERE `profile`.`class_id` = 9
  AND `profile`.`spec_tag` = 'affliction_warlock'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 6353;
