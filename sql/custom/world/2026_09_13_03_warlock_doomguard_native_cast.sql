-- DPS-053: temporary entry-11859 guardian casts native Doom Bolt under owner authority.
-- Preserve summon properties, duration, stats, primary pet, and native spell data.
UPDATE creature_template
SET AIName = '', ScriptName = 'npc_pet_warlock_doomguard',
    spell1 = 85692, spell2 = 0, spell3 = 0, spell4 = 0,
    spell5 = 0, spell6 = 0, spell7 = 0, spell8 = 0
WHERE entry = 11859;
