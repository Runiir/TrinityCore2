-- Passive command and position observations. No command submission or setters.
local function call(fn,...)
    if type(fn)~='function' then return nil end
    local ok,value=pcall(fn,...)
    if ok then return value end
end
local function position(unit)
    if type(UnitPosition)~='function' then return {available=false} end
    local ok,x,y,z,map=pcall(UnitPosition,unit)
    local available=ok and type(x)=='number' and type(y)=='number' and type(z)=='number'
        and type(map)=='number' and x==x and y==y and z==z
        and math.abs(x)<=17067 and math.abs(y)<=17067 and math.abs(z)<=17067
    if not available then return {available=false} end
    return {available=true,x=x,y=y,z=z,map=map}
end
function Client442ObservePetCommands()
    local rows={}
    for slot=1,10 do
        local ok,name,texture,token,active,autoAllowed,autoEnabled,spell
        if type(GetPetActionInfo)=='function' then
            ok,name,texture,token,active,autoAllowed,autoEnabled,spell=pcall(GetPetActionInfo,slot)
        end
        rows[#rows+1]={slot=slot,available=not not ok,name=ok and name or nil,
            texture=ok and texture or nil,is_token=ok and not not token or false,
            active=ok and not not active or false,autocast_allowed=ok and not not autoAllowed or false,
            autocast_enabled=ok and not not autoEnabled or false,spell_id=ok and spell or nil}
    end
    local player,pet=position('player'),position('pet')
    local ranges={}
    for index=1,4 do
        local value=call(CheckInteractDistance,'pet',index)
        ranges[#ranges+1]={index=index,available=type(value)=='boolean',in_range=value}
    end
    local squared={available=false}
    if type(UnitDistanceSquared)=='function' then
        local ok,value,checked=pcall(UnitDistanceSquared,'pet')
        if ok and checked and type(value)=='number' and value==value and value>=0 and value<math.huge then
            squared={available=true,value=value,checked=not not checked}
        end
    end
    local distance
    if player.available and pet.available and player.map==pet.map then
        distance=math.sqrt((player.x-pet.x)^2+(player.y-pet.y)^2+(player.z-pet.z)^2)
    end
    return {owner_guid=call(UnitGUID,'player'),pet_guid=call(UnitGUID,'pet'),
        actions=rows,player_position=player,pet_position=pet,distance=distance,
        interaction_ranges=ranges,distance_squared=squared,pet_visible=call(UnitIsVisible,'pet'),
        player_speed=call(GetUnitSpeed,'player'),pet_speed=call(GetUnitSpeed,'pet')}
end
