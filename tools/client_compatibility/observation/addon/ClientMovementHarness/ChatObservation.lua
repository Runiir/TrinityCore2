-- Public local chat-window settings. No chat/window setters or message sends.
local function read(fn,...)
    if type(fn)~='function' then return end
    local ok,a,b,c,d,e,f,g,h,i,j=pcall(fn,...)
    if ok then return a,b,c,d,e,f,g,h,i,j end
end
function Client442ObserveChatWindows()
    local result={available=type(GetChatWindowInfo)=='function',windows={}}
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
    return result
end
