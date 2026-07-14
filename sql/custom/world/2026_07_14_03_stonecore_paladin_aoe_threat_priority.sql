-- Run 087 kept every bot alive but the protection paladin retained only 77%
-- of sampled multi-target victims during the large Devout Follower wave.
-- Prefer the normal Cataclysm AoE threat toolkit before single-target spenders
-- whenever the profile observes multiple enemies. Boss/single-target ordering
-- is unchanged because these actions retain their min_enemies = 2 gates.
UPDATE `bot_rotation_action` AS `action`
JOIN `bot_rotation_profile` AS `profile` ON `profile`.`id` = `action`.`profile_id`
SET `action`.`priority_bucket` = CASE
    WHEN `action`.`spell_id` IN (53595, 26573) THEN 1
    ELSE 2
END
WHERE `profile`.`class_id` = 2
  AND `profile`.`spec_tag` = 'protection'
  AND `profile`.`role` = 'tank'
  AND `action`.`spell_id` IN (53595, 26573, 2812);
