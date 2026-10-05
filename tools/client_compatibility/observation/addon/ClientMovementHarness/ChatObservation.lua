-- Public local chat-window settings. No chat/window setters or message sends.
local function read(fn,...)
    if type(fn)~='function' then return end
    local ok,a,b,c,d,e,f,g,h,i,j=pcall(fn,...)
    if ok then return a,b,c,d,e,f,g,h,i,j end
end
function Client442ObserveChatWindows()
    local result={available=type(GetChatWindowInfo)=='function',windows={}}
    if type(Client442ObserveChannelList)=='function' then result.channel_list=Client442ObserveChannelList() end
    result.channels={available=false,rows={}}
    if type(GetChannelList)=='function' then
        local values={pcall(GetChannelList)}
        if values[1] and (#values-1)%3==0 and #values<=25 then
            result.channels.available=true
            for index=2,#values,3 do
                local id,name,disabled=values[index],values[index+1],values[index+2]
                if type(id)~='number' or type(name)~='string' or type(disabled)~='boolean' then
                    result.channels.available=false;result.channels.error='unsupported public channel tuple';break
                end
                result.channels.rows[#result.channels.rows+1]={id=id,name=name:sub(1,80),disabled=disabled}
            end
        else result.channels.error='public channel list failed or exceeds eight-channel observation bound' end
    end
    for index=1,math.min(tonumber(NUM_CHAT_WINDOWS) or 10,10) do
        local name,size,r,g,b,alpha,shown,locked,docked,uninteractable=read(GetChatWindowInfo,index)
        local frame=_G['ChatFrame'..index]
        local tab=_G['ChatFrame'..index..'Tab']
        local font,fontSize,flags
        if frame then font,fontSize,flags=read(frame.GetFont,frame) end
        result.windows[#result.windows+1]={id=index,name=name,font_size=size,color={r,g,b},alpha=alpha,
            shown=shown,locked=locked,docked=docked,uninteractable=uninteractable,
            frame_visible=frame and read(frame.IsVisible,frame),tab_visible=tab and read(tab.IsVisible,tab),
            actual_font=font,actual_font_size=fontSize,font_flags=flags,
            message_count=frame and read(frame.GetNumMessages,frame),
            scroll_offset=frame and read(frame.GetScrollOffset,frame)}
    end
    result.selected=SELECTED_CHAT_FRAME and read(SELECTED_CHAT_FRAME.GetID,SELECTED_CHAT_FRAME)
    result.settings_visible=ChatConfigFrame and read(ChatConfigFrame.IsVisible,ChatConfigFrame) or false
    result.config_window_id=result.settings_visible and tonumber(CURRENT_CHAT_FRAME_ID) or nil
    local selected=_G['ChatFrame'..tostring(result.config_window_id or result.selected or 1)]
    result.selected_height=selected and read(selected.GetHeight,selected)
    result.selected_width=selected and read(selected.GetWidth,selected)
    result.message_types={}
    result.message_types_available=selected and type(selected.messageTypeList)=='table' or false
    if result.message_types_available then
        for _,value in pairs(selected.messageTypeList) do
            if type(value)=='string' and #result.message_types<128 then
                result.message_types[#result.message_types+1]=value
            end
        end
        table.sort(result.message_types)
    end
    return result
end
