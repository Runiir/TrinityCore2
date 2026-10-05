local events,sequence={},0
local listener
if type(CreateFrame)=='function' then
    listener=CreateFrame('Frame')
    if listener then
        listener:RegisterEvent('CHAT_MSG_CHANNEL_LIST')
        listener:SetScript('OnEvent',function(_,event,...)
            local args={...}
            local channel=type(args[9])=='string' and args[9] or type(args[4])=='string' and args[4] or ''
            if not channel:find('TC442UIChannel',1,true) then return end
            sequence=sequence+1
            local text=type(args[1])=='string' and args[1] or ''
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
    return {registered=registered,stock_registered=stockRegistered,sequence=sequence,events=events}
end
