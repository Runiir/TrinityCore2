-- Read stock recipe viewport and scrollbar geometry. No selection/filter setters.
local function call(f,...)
    if type(f)~='function' then return end
    local ok,a,b=pcall(f,...);if ok then return a,b end
end
function Client442ObserveTradeSkill()
    local frame,slider=TradeSkillFrame,TradeSkillListScrollFrameScrollBar
    local data={visible=frame and not not call(frame.IsVisible,frame) or false,rows={}}
    if not data.visible then return data end
    data.count=call(GetNumTradeSkills);data.selection=call(GetTradeSkillSelectionIndex)
    data.offset=call(FauxScrollFrame_GetOffset,TradeSkillListScrollFrame)
    local width=GetScreenWidth()*UIParent:GetEffectiveScale()
    local height=GetScreenHeight()*UIParent:GetEffectiveScale()
    if slider then
        local low,high=call(slider.GetMinMaxValues,slider)
        local thumb=call(slider.GetThumbTexture,slider)
        local scale=call(slider.GetEffectiveScale,slider)
        local top,bottom=call(slider.GetTop,slider),call(slider.GetBottom,slider)
        local x,y
        if thumb then x,y=call(thumb.GetCenter,thumb) end
        local thumbScale=thumb and (call(thumb.GetEffectiveScale,thumb) or scale)
        local thumbHeight=thumb and call(thumb.GetHeight,thumb)
        if scale and top and bottom and x and y and thumbScale and thumbHeight then
            local half=thumbHeight*thumbScale/height/2
            data.slider={name=call(slider.GetName,slider),low=low,high=high,value=call(slider.GetValue,slider),
                thumb={x=x*thumbScale/width*65535,y=(1-y*thumbScale/height)*65535},
                track_top=(1-top*scale/height+half)*65535,
                track_bottom=(1-bottom*scale/height-half)*65535}
        end
    end
    for i=1,8 do
        local button=_G['TradeSkillSkill'..i];local text=_G['TradeSkillSkill'..i..'Text']
        if button and call(button.IsVisible,button) then
            data.rows[#data.rows+1]={button=call(button.GetName,button),index=call(button.GetID,button),
                text=text and call(text.GetText,text)}
        end
    end
    return data
end
