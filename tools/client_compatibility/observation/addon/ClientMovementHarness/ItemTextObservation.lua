-- Passive stock readable-item state and event observations. No gameplay calls.
local function call(f,...)
    if type(f)~='function' then return end
    local ok,value=pcall(f,...);if ok then return value end
end
local function visible(frame) return frame and not not call(frame.IsVisible,frame) or false end
local counts={ITEM_TEXT_BEGIN=0,ITEM_TEXT_READY=0,ITEM_TEXT_CLOSED=0,ITEM_TEXT_TRANSLATION=0}
local events={}
local observer=CreateFrame('Frame')
for event in pairs(counts) do observer:RegisterEvent(event) end
observer:SetScript('OnEvent',function(_,event)
    counts[event]=counts[event]+1
    events[#events+1]={event=event,time=call(GetTime),page=call(ItemTextGetPage)}
    if #events>8 then table.remove(events,1) end
end)
function Client442ObserveItemText()
    local text=call(ItemTextGetText)
    local length=type(text)=='string' and #text or 0
    return {visible=visible(ItemTextFrame),contents_visible=visible(ItemTextScrollFrame),
        title=ItemTextTitleText and call(ItemTextTitleText.GetText,ItemTextTitleText),
        item=call(ItemTextGetItem),page=call(ItemTextGetPage),has_next=not not call(ItemTextHasNextPage),
        material=call(ItemTextGetMaterial),creator=call(ItemTextGetCreator),
        text=type(text)=='string' and text:sub(1,2048) or nil,text_length=length,text_truncated=length>2048,
        previous_visible=visible(ItemTextPrevPageButton),next_visible=visible(ItemTextNextPageButton),
        events=events,event_counts=counts}
end
