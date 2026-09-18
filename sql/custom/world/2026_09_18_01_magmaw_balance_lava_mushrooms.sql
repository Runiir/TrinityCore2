-- Magmaw 10N Balance add-duty contract.
--
-- Wild Mushroom is an encounter action here, not a prepull fixture action:
-- when the Balance bot is targeting a Lava Parasite, the native resolver puts
-- three mushrooms at the parasite's spawn/home position and then selects
-- Detonate before returning to the ordinary profile.  The resolver still
-- owns the route, target, count, Eclipse, and area-safety gates.

SET @balance_profile := (
    SELECT `id`
    FROM `bot_rotation_profile`
    WHERE `class_id` = 11
      AND `spec_tag` = 'balance_druid'
      AND `role` = 'dps'
    LIMIT 1
);

UPDATE `bot_rotation_action`
SET `mechanic_tags` = 'wild_mushroom,magmaw_lava_parasite_add_duty,pinned_apl',
    `target_selector` = 'ground_enemy',
    `requires_ground_target` = 1
WHERE `profile_id` = @balance_profile
  AND `spell_id` = 88747
  AND `enabled` = 1;

UPDATE `bot_rotation_action`
SET `mechanic_tags` = 'wild_mushroom_detonate,solar_eclipse,magmaw_lava_parasite_add_duty,pinned_apl',
    `target_selector` = 'self',
    `requires_ground_target` = 0
WHERE `profile_id` = @balance_profile
  AND `spell_id` = 88751
  AND `enabled` = 1;
