-- Read the exact legacy lesson and learned ability. No gameplay or cache writes.
local function call(fn,...)
    if type(fn)~='function' then return nil end
    local ok,value=pcall(fn,...)
    if ok then return value end
end
local function spell(id)
    local modern=call(C_Spell and C_Spell.GetSpellInfo,id)
    return {id=id,name=type(modern)=='table' and modern.name or call(GetSpellInfo,id),
        api_id=type(modern)=='table' and modern.spellID or nil,
        info_available=modern~=nil,known=call(IsSpellKnown,id)}
end
function Client442ObserveControlDemon()
    return {lesson=spell(80388),learned=spell(93375)}
end
