-- Observe native-delivered stock swing events. Never submit or synthesize them.
local events,sequence={},0
local reader=CreateFrame('Frame')
local registered=pcall(reader.RegisterEvent,reader,'COMBAT_LOG_EVENT_UNFILTERED')
reader:SetScript('OnEvent',function(_,dispatch,...)
    local fn=C_CombatLog and C_CombatLog.GetCurrentEventInfo or CombatLogGetCurrentEventInfo
    local values={...};local source='event_arguments'
    if type(fn)=='function' then
        values={pcall(fn)};if not values[1] then return end
        table.remove(values,1)
        source=C_CombatLog and fn==C_CombatLog.GetCurrentEventInfo and
            'C_CombatLog.GetCurrentEventInfo' or 'CombatLogGetCurrentEventInfo'
    end
    local kind=values[2]
    if values[4]~=UnitGUID('player') or (kind~='SWING_DAMAGE' and kind~='SWING_MISSED') then return end
    sequence=sequence+1
    local row={sequence=sequence,timestamp=values[1],event=kind,source_guid=values[4],
        destination_guid=values[8],reader=source,dispatch=dispatch}
    if kind=='SWING_DAMAGE' then
        row.amount=values[12];row.overkill=values[13];row.school=values[14]
        row.resisted=values[15];row.blocked=values[16];row.absorbed=values[17]
        row.critical=not not values[18];row.glancing=not not values[19]
        row.crushing=not not values[20];row.offhand=not not values[21]
    else
        row.miss_type=values[12];row.offhand=not not values[13];row.amount_missed=values[14]
    end
    events[#events+1]=row;if #events>4 then table.remove(events,1) end
end)
function Client442ObserveMelee()
    return {event_registered=registered,event_sequence=sequence,events=events,
        active=type(IsCurrentSpell)=='function' and not not IsCurrentSpell(6603) or false}
end
