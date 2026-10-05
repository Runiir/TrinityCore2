-- Read selected stock combat-log text and attributable public combat events.
-- This frame never submits actions, changes filters, or inserts log messages.
local events,sequence={},0
local reader=CreateFrame('Frame')
local registered=pcall(reader.RegisterEvent,reader,'COMBAT_LOG_EVENT')
reader:SetScript('OnEvent',function(_,event,...)
    local fn=C_CombatLog and C_CombatLog.GetCurrentEventInfo or CombatLogGetCurrentEventInfo
    local values={...};local source='event_arguments'
    if type(fn)=='function' then
        values={pcall(fn)};if not values[1] then return end
        table.remove(values,1);source=C_CombatLog and fn==C_CombatLog.GetCurrentEventInfo and
            'C_CombatLog.GetCurrentEventInfo' or 'CombatLogGetCurrentEventInfo'
    end
    if values[12]~=6673 or values[4]~=UnitGUID('player') then return end
    sequence=sequence+1
    events[#events+1]={sequence=sequence,timestamp=values[1],event=values[2],source_guid=values[4],
        destination_guid=values[8],spell_id=values[12],spell_name=values[13],reader=source}
    if #events>4 then table.remove(events,1) end
end)
local function read(fn,...)
    if type(fn)~='function' then return end
    local ok,value=pcall(fn,...);if ok then return value end
end
function Client442ObserveCombatLog()
    local log=ChatFrame2;local count=log and read(log.GetNumMessages,log)
    local result={event_registered=registered,event_sequence=sequence,events=events,
        selected=SELECTED_CHAT_FRAME and read(SELECTED_CHAT_FRAME.GetID,SELECTED_CHAT_FRAME),
        visible=log and read(log.IsVisible,log),message_count=count,recent_messages={}}
    result.text_reader_available=log and type(log.GetMessageInfo)=='function' or false
    for index=math.max(1,(tonumber(count) or 0)-3),tonumber(count) or 0 do
        local text=read(log.GetMessageInfo,log,index)
        if type(text)=='string' then
            local position=text:find('Battle Shout',1,true)
            local first=position and math.max(1,position-160) or 1
            result.recent_messages[#result.recent_messages+1]={index=index,text=text:sub(first,first+319),
                contains_battle_shout=not not position,truncated=#text>320}
        end
    end
    return result
end
