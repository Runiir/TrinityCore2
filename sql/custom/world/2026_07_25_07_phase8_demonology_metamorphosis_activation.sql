-- Phase 8 Demonology Warlock Metamorphosis aura contract.
--
-- Spell 59672 is the passive talent spell that teaches Metamorphosis actions;
-- the runtime action remains 47241 and applies aura 47241. Gate Immolation Aura
-- on that live transformation aura rather than on the passive teaching spell.

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`spell_id` = 47241,
    `action`.`maintain_aura_id` = 47241,
    `action`.`mechanic_tags` = 'metamorphosis,burst,pinned_apl'
WHERE `profile`.`class_id` = 9
  AND `profile`.`spec_tag` = 'demonology_warlock'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` IN (47241, 59672);

UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile`
  ON `profile`.`id` = `action`.`profile_id`
SET `action`.`required_self_aura` = 47241
WHERE `profile`.`class_id` = 9
  AND `profile`.`spec_tag` = 'demonology_warlock'
  AND `profile`.`role` = 'dps'
  AND `action`.`spell_id` = 50589;
