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
local function casting(unit)
    if type(UnitCastingInfo)~='function' then return {available=false} end
    local ok,name,_,_,started,finished,trade,identity,uninterruptible,spell=pcall(UnitCastingInfo,unit)
    if not ok then return {available=false} end
    return {available=true,active=name~=nil,name=name,started_ms=started,finished_ms=finished,
        trade_skill=trade,cast_id=identity,uninterruptible=uninterruptible,spell=spell}
end
local function frame(slot,width,height)
    local button=_G['PetActionButton'..slot]
    local row={button='PetActionButton'..slot,available=false,visible=false,enabled=false,checked=false}
    if not button then return row end
    row.visible=not not call(button.IsVisible,button)
    row.enabled=not not call(button.IsEnabled,button)
    row.checked=not not call(button.GetChecked,button)
    local scale=call(button.GetEffectiveScale,button)
    if type(button.GetCenter)~='function' or type(scale)~='number' or scale<=0 or not width or not height then return row end
    local ok,x,y=pcall(button.GetCenter,button)
    if not ok or type(x)~='number' or type(y)~='number' or x~=x or y~=y then return row end
    x,y=x*scale/width,1-y*scale/height
    if x<0 or x>1 or y<0 or y>1 then return row end
    row.available=true;row.x=math.floor(x*65535);row.y=math.floor(y*65535)
    return row
end
function Client442ObservePetCommands()
    local rows={}
    local scale=UIParent and call(UIParent.GetEffectiveScale,UIParent)
    local width,height=call(GetScreenWidth),call(GetScreenHeight)
    if type(scale)=='number' and scale>0 and type(width)=='number' and width>0 and type(height)=='number' and height>0 then
        width,height=scale*width,scale*height
    else width,height=nil,nil end
    for slot=1,10 do
        local ok,name,texture,token,active,autoAllowed,autoEnabled,spell
        if type(GetPetActionInfo)=='function' then
            ok,name,texture,token,active,autoAllowed,autoEnabled,spell=pcall(GetPetActionInfo,slot)
        end
        rows[#rows+1]={slot=slot,available=not not ok,name=ok and name or nil,
            texture=ok and texture or nil,is_token=ok and not not token or false,
            active=ok and not not active or false,autocast_allowed=ok and not not autoAllowed or false,
            autocast_enabled=ok and not not autoEnabled or false,spell_id=ok and spell or nil,
            usable=call(GetPetActionSlotUsable,slot),
            frame=frame(slot,width,height)}
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
        modified_click=call(IsModifiedClick),
        actions=rows,viewport={width=width,height=height,basis='scaled_game_ui_screen'},
        player_position=player,pet_position=pet,distance=distance,
        interaction_ranges=ranges,distance_squared=squared,pet_visible=call(UnitIsVisible,'pet'),
        pet_combat=call(UnitAffectingCombat,'pet'),pet_cast=casting('pet'),pet_target_exists=call(UnitExists,'pettarget'),
        pet_target_guid=call(UnitGUID,'pettarget'),pet_target_name=call(UnitName,'pettarget'),
        player_can_attack_target=call(UnitCanAttack,'player','target'),
        player_speed=call(GetUnitSpeed,'player'),pet_speed=call(GetUnitSpeed,'pet')}
end
