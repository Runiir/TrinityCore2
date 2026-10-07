-- Observe the client's actual channel API and events. Never cast or emit events.
local events,sequence={},0
local reader=CreateFrame('Frame')
for _,event in ipairs({'UNIT_SPELLCAST_CHANNEL_START','UNIT_SPELLCAST_CHANNEL_UPDATE',
    'UNIT_SPELLCAST_CHANNEL_STOP'}) do reader:RegisterEvent(event) end
local function current()
    local name=type(UnitChannelInfo)=='function' and UnitChannelInfo('player') or nil
    return {active=name~=nil,name=name}
end
reader:SetScript('OnEvent',function(_,event,unit,castID,spell)
    if unit~='player' then return end
    sequence=sequence+1
    events[#events+1]={sequence=sequence,event=event,cast_id=castID,spell=spell,
        observed_at=GetTime(),channel=current()}
    if #events>4 then table.remove(events,1) end
end)
function Client442ObserveSpellChannel()
    local state=current();state.event_sequence=sequence;state.events=events
    return state
end
