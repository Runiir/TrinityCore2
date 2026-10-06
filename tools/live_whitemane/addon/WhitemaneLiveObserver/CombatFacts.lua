-- Read actual attackers; never chooses or changes a target.
local recent={}
local function call(fn,...)
    if type(fn)~='function' then return end
    local ok,a,b,c=pcall(fn,...);if ok then return a,b,c end
end
local event=CreateFrame('Frame')
event:RegisterEvent('COMBAT_LOG_EVENT_UNFILTERED')
event:RegisterEvent('PLAYER_REGEN_ENABLED')
event:SetScript('OnEvent',function(_,kind)
    if kind=='PLAYER_REGEN_ENABLED' then recent={};return end
    if type(CombatLogGetCurrentEventInfo)~='function' then return end
    local _,subevent,_,source,_,_,_,destination=CombatLogGetCurrentEventInfo()
    if source and source~=UnitGUID('player') and destination==UnitGUID('player') and
        (subevent:find('_DAMAGE$',1) or subevent:find('_MISSED$',1)) then
        local now=GetTime();recent[source]=now
        local count=0
        for guid,at in pairs(recent) do
            if now-at>20 then recent[guid]=nil else count=count+1 end
        end
        if count>16 then
            local oldest,at
            for guid,time in pairs(recent) do if not at or time<at then oldest,at=guid,time end end
            if oldest then recent[oldest]=nil end
        end
    end
end)
local function engaged(unit)
    local guid=call(UnitGUID,unit)
    return guid and call(UnitCanAttack,'player',unit) and not call(UnitIsDeadOrGhost,unit) and
        (call(UnitIsUnit,unit..'target','player') or
         (call(UnitAffectingCombat,unit) and recent[guid] and GetTime()-recent[guid]<=20)) or false
end
function WhitemaneLiveCombatFacts()
    local attackers={}
    local uiScale=UIParent:GetEffectiveScale()
    local width,height=GetScreenWidth()*uiScale,GetScreenHeight()*uiScale
    for _,plate in ipairs(call(C_NamePlate and C_NamePlate.GetNamePlates) or {}) do
        local unit=plate.namePlateUnitToken or plate.UnitFrame and plate.UnitFrame.unit
        if unit and plate:IsShown() and engaged(unit) then
            local x,y=plate:GetCenter()
            local scale=plate:GetEffectiveScale()
            if x and y and width and height and width>0 and height>0 then
                x,y=x*scale/width,1-y*scale/height
                if x>0 and x<1 and y>0 and y<1 then
                    attackers[#attackers+1]={unit=unit,guid=UnitGUID(unit),name=UnitName(unit),x=x,y=y}
                end
            end
        end
    end
    table.sort(attackers,function(a,b)return a.guid<b.guid end)
    while #attackers>4 do table.remove(attackers) end
    return {target_engaged=not not engaged('target'),attackers=attackers}
end
