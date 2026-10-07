-- Passive stock stable cache, model and event readings. No stable API writes.
local function call(fn,...)
    if type(fn)~='function' then return nil end
    local ok,a,b,c,d,e=pcall(fn,...)
    if ok then return a,b,c,d,e end
end
local events,sequence={},0
local frame=CreateFrame('Frame')
for _,event in ipairs({'PET_STABLE_SHOW','PET_STABLE_UPDATE','PET_STABLE_UPDATE_PAPERDOLL','PET_STABLE_CLOSED'}) do
    frame:RegisterEvent(event)
end
frame:SetScript('OnEvent',function(_,event)
    sequence=sequence+1;events[event]={sequence=sequence,count=(events[event] and events[event].count or 0)+1}
end)
function Client442ObserveStables()
    local stable=PetStableFrame
    local data={visible=stable and stable:IsVisible() or false,events=events,event_sequence=sequence,
        page=stable and stable.page,selected=stable and stable.selectedPet,
        stable_slots=call(GetNumStableSlots),pets={},buttons={}}
    if not data.visible then return data end
    for slot=1,205 do
        local icon,name,level,family,talent=call(GetStablePetInfo,slot)
        if name then
            data.pets[#data.pets+1]={slot=slot,icon=icon,name=name,level=level,family=family,talent=talent,
                display_id=call(C_PlayerInfo and C_PlayerInfo.GetPetStableCreatureDisplayInfoID,slot)}
        end
    end
    for _,prefix in ipairs({'PetStableActivePet','PetStableStabledPet'}) do
        for i=1,(prefix=='PetStableActivePet' and 5 or 10) do
            local name=prefix..i;local button=_G[name]
            if button then
                local x,y=button:GetCenter();local w,h=UIParent:GetSize()
                data.buttons[#data.buttons+1]={name=name,slot=button.petSlot,visible=button:IsVisible(),
                    enabled=button:IsEnabled(),x=x and math.floor(x/w*65535),y=y and math.floor((1-y/h)*65535)}
            end
        end
    end
    data.name=call(PetStableNameText and PetStableNameText.GetText,PetStableNameText)
    data.level=call(PetStableLevelText and PetStableLevelText.GetText,PetStableLevelText)
    return data
end
