-- Read selected stock combat-log text and attributable public combat events.
-- This frame never submits actions, changes filters, or inserts log messages.
local events,sequence={},0
local reader=CreateFrame('Frame')
local registered=pcall(reader.RegisterEvent,reader,'COMBAT_LOG_EVENT')
local unfiltered=pcall(reader.RegisterEvent,reader,'COMBAT_LOG_EVENT_UNFILTERED')
reader:SetScript('OnEvent',function(_,event,...)
    local fn=C_CombatLog and C_CombatLog.GetCurrentEventInfo or CombatLogGetCurrentEventInfo
    local values={...};local source='event_arguments'
    if type(fn)=='function' then
        values={pcall(fn)};if not values[1] then return end
        table.remove(values,1);source=C_CombatLog and fn==C_CombatLog.GetCurrentEventInfo and
            'C_CombatLog.GetCurrentEventInfo' or 'CombatLogGetCurrentEventInfo'
    end
    if (values[12]~=6673 and values[12]~=57755) or values[4]~=UnitGUID('player') then return end
    sequence=sequence+1
    events[#events+1]={sequence=sequence,timestamp=values[1],event=values[2],source_guid=values[4],
        destination_guid=values[8],spell_id=values[12],spell_name=values[13],reader=source,dispatch=event}
    if values[2]=='SPELL_DAMAGE' then
        local row=events[#events]
        row.amount=values[15];row.overkill=values[16];row.school=values[17]
        row.resisted=values[18];row.blocked=values[19];row.absorbed=values[20]
        row.critical=not not values[21]
    end
    if #events>4 then table.remove(events,1) end
end)
local function read(fn,...)
    if type(fn)~='function' then return end
    local ok,value=pcall(fn,...);if ok then return value end
end
local function fingerprint(value)
    local nodes,first,second=0,0,0
    local function feed(text)
        for index=1,#text do
            local byte=text:byte(index)
            first=(first*33+byte)%4294967291;second=(second*65599+byte)%4294967279
        end
    end
    local active={}
    local function visit(item,depth)
        nodes=nodes+1;if nodes>8192 or depth>16 then error('public saved settings exceed the observation bound') end
        local kind=type(item);feed(kind..':')
        if kind=='table' then
            if active[item] then error('cyclic public saved settings') end;active[item]=true
            local keys={};for key in pairs(item) do keys[#keys+1]=key end
            table.sort(keys,function(a,b)return type(a)..':'..tostring(a)<type(b)..':'..tostring(b) end)
            feed('{');for _,key in ipairs(keys) do visit(key,depth+1);visit(item[key],depth+1) end;feed('}')
            active[item]=nil
        elseif kind=='string' then feed(#item..':'..item)
        elseif kind=='number' then feed(string.format('%.17g',item))
        elseif kind=='boolean' or kind=='nil' then feed(tostring(item))
        else error('unsupported public saved-setting type') end
        feed(';')
    end
    local ok,why=pcall(visit,value,0)
    return {available=ok and type(value)=='table',nodes=nodes,first=ok and first or nil,
        second=ok and second or nil,error=not ok and tostring(why) or nil}
end
function Client442ObserveCombatLog()
    local log=ChatFrame2;local count=log and read(log.GetNumMessages,log)
    local settingsVisible=ChatConfigFrame and read(ChatConfigFrame.IsVisible,ChatConfigFrame) or false
    local selected=settingsVisible and CHATCONFIG_SELECTED_FILTER or Blizzard_CombatLog_CurrentSettings
    local result={event_registered=registered and read(reader.IsEventRegistered,reader,'COMBAT_LOG_EVENT') or false,
        unfiltered_registered=unfiltered and read(reader.IsEventRegistered,reader,'COMBAT_LOG_EVENT_UNFILTERED') or false,
        event_sequence=sequence,events=events,
        selected=SELECTED_CHAT_FRAME and read(SELECTED_CHAT_FRAME.GetID,SELECTED_CHAT_FRAME),
        visible=log and read(log.IsVisible,log),message_count=count,recent_messages={},
        saved_settings=fingerprint(Blizzard_CombatLog_Filters),filter_name=selected and selected.name,
        current_filter=Blizzard_CombatLog_Filters and Blizzard_CombatLog_Filters.currentFilter,
        settings_filter=ChatConfigCombatSettingsFilters and ChatConfigCombatSettingsFilters.selectedFilter,
        cast_success_enabled={},filters={},settings_visible=settingsVisible}
    for index,filter in ipairs(Blizzard_CombatLog_Filters and Blizzard_CombatLog_Filters.filters or {}) do
        result.filters[#result.filters+1]={id=index,name=filter.name,quick_button=filter.hasQuickButton}
    end
    for index,filter in ipairs(selected and selected.filters or {}) do
        result.cast_success_enabled[index]=filter.eventList and filter.eventList.SPELL_CAST_SUCCESS or false
    end
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
