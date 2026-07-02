UPDATE `bot_rotation_action` a
JOIN `bot_rotation_profile` p ON p.`id` = a.`profile_id`
SET a.`max_target_health_pct` = CASE
  WHEN p.`class_id` = 11 AND p.`spec_tag` = 'restoration_druid' AND a.`spell_id` = 8936 THEN 0.82
  WHEN p.`class_id` = 11 AND p.`spec_tag` = 'restoration_druid' AND a.`spell_id` = 5185 THEN 0.92
  WHEN p.`class_id` = 2 AND p.`spec_tag` = 'holy_paladin' AND a.`spell_id` = 19750 THEN 0.82
  WHEN p.`class_id` = 2 AND p.`spec_tag` = 'holy_paladin' AND a.`spell_id` = 635 THEN 0.94
  WHEN p.`class_id` = 5 AND p.`spec_tag` = 'discipline_priest' AND a.`spell_id` = 2061 THEN 0.82
  WHEN p.`class_id` = 5 AND p.`spec_tag` = 'discipline_priest' AND a.`spell_id` = 2050 THEN 0.94
  ELSE a.`max_target_health_pct`
END
WHERE p.`role` = 'healer'
  AND (
    (p.`class_id` = 11 AND p.`spec_tag` = 'restoration_druid' AND a.`spell_id` IN (8936, 5185))
    OR (p.`class_id` = 2 AND p.`spec_tag` = 'holy_paladin' AND a.`spell_id` IN (19750, 635))
    OR (p.`class_id` = 5 AND p.`spec_tag` = 'discipline_priest' AND a.`spell_id` IN (2061, 2050))
  );
