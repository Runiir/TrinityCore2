local events,sequence,received={},0,0
local listener
if type(CreateFrame)=='function' then
    listener=CreateFrame('Frame')
    if listener then
        listener:RegisterEvent('CHAT_MSG_CHANNEL_LIST')
        listener:RegisterEvent('CHANNEL_ROSTER_UPDATE')
        listener:SetScript('OnEvent',function(_,event,...)
            local args={...}
            received=received+1
            local channel=''
            for _,index in ipairs({9,4}) do
                if type(args[index])=='string' and args[index]:find('TC442UIChannel',1,true) then channel=args[index];break end
            end
            if event=='CHANNEL_ROSTER_UPDATE' and type(GetChannelDisplayInfo)=='function' and type(args[1])=='number' then
                local ok,name=pcall(GetChannelDisplayInfo,args[1])
                if ok and type(name)=='string' then channel=name end
            end
            if not channel:find('TC442UIChannel',1,true) then return end
            sequence=sequence+1
            local text=event=='CHAT_MSG_CHANNEL_LIST' and type(args[1])=='string' and args[1] or ''
            events[#events+1]={sequence=sequence,event=event,channel=channel:sub(1,80),
                text=text:sub(1,160),text_length=#text,truncated=#text>160,index=tonumber(args[8])}
            while #events>2 do table.remove(events,1) end
        end)
    end
end

function Client442ObserveChannelList()
    local registered=false
    if listener and type(listener.IsEventRegistered)=='function' then
        local ok,value=pcall(listener.IsEventRegistered,listener,'CHAT_MSG_CHANNEL_LIST')
        registered=ok and value==true
    end
    local stockRegistered
    if ChatFrame1 and type(ChatFrame1.IsEventRegistered)=='function' then
        local ok,value=pcall(ChatFrame1.IsEventRegistered,ChatFrame1,'CHAT_MSG_CHANNEL_LIST')
        if ok then stockRegistered=value==true end
    end
    local roster={available=false,channels={}}
    if type(GetNumDisplayChannels)=='function' and type(GetChannelDisplayInfo)=='function' and
            C_ChatInfo and type(C_ChatInfo.GetChannelRosterInfo)=='function' then
        local ok,count=pcall(GetNumDisplayChannels)
        if ok and type(count)=='number' and count>=0 and count<=24 then
            roster.available=true
            for id=1,count do
                local success,name,header,collapsed,channelNumber,members=pcall(GetChannelDisplayInfo,id)
                if success and type(name)=='string' and name:find('TC442UIChannel',1,true) then
                    local row={display_id=id,name=name:sub(1,80),channel_number=channelNumber,member_count=members,members={}}
                    if type(members)=='number' and members>=0 and members<=2 then
                        for index=1,members do
                            local success,memberName,owner,moderator,guid=pcall(C_ChatInfo.GetChannelRosterInfo,id,index)
                            if success and type(memberName)=='string' then
                                local playerGUID=type(UnitGUID)=='function' and UnitGUID('player') or nil
                                row.members[#row.members+1]={name=memberName:sub(1,80),owner=owner,moderator=moderator,
                                    guid=type(guid)=='string' and guid:sub(1,80) or nil,is_player=playerGUID~=nil and guid==playerGUID}
                            end
                        end
                    end
                    roster.channels[#roster.channels+1]=row
                end
            end
        end
    end
    return {registered=registered,stock_registered=stockRegistered,sequence=sequence,received_sequence=received,events=events,roster=roster}
end
