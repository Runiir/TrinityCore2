-- Installed Cata TokenUI reads only. No currency or stock UI mutations.
local function call(fn,...)
    if type(fn)~='function' then return nil end
    local ok,a,b,c,d,e,f,g=pcall(fn,...)
    if ok then return a,b,c,d,e,f,g end
end
local function info(id)
    local value=call(C_CurrencyInfo and C_CurrencyInfo.GetCurrencyInfo,id)
    if type(value)~='table' then return nil end
    local out={}
    for _,key in ipairs({'name','quantity','trackedQuantity','maxQuantity',
        'quantityEarnedThisWeek','maxWeeklyQuantity','discovered','isTypeUnused',
        'isShowInBackpack','canEarnPerWeek'}) do out[key]=value[key] end
    return out
end
local function currency(index)
    local name,header,expanded,unused,watched,count,icon=call(GetCurrencyListInfo,index)
    if not name then return nil end
    local link=call(C_CurrencyInfo and C_CurrencyInfo.GetCurrencyListLink,index)
    local id=type(link)=='string' and tonumber(link:match('currency:(%d+)')) or nil
    return {index=index,name=name,header=not not header,expanded=not not expanded,
        unused=not not unused,watched=not not watched,count=count,icon=icon,
        id=id,info=id and info(id) or nil}
end
function Client442ObserveCurrency(page)
    local count=call(GetCurrencyListSize) or 0
    local data={count=count,page=page,rows={},controls={},backpack={},visible_rows={}}
    for index=(page-1)*8+1,math.min(page*8,count) do
        local row=currency(index);if row then data.rows[#data.rows+1]=row end
    end
    data.selected_index=TokenFrame and TokenFrame.selectedID
    if data.selected_index then data.selected=currency(data.selected_index) end
    for _,key in ipairs({'TokenFrame','TokenFramePopup','TokenFramePopupInactiveCheckbox',
        'TokenFramePopupBackpackCheckbox','BackpackTokenFrame'}) do
        local f=_G[key]
        if f then data.controls[#data.controls+1]={name=key,visible=not not call(f.IsVisible,f),
            enabled=call(f.IsEnabled,f),checked=f.GetChecked and not not call(f.GetChecked,f) or false} end
    end
    for _,button in ipairs(TokenFrameContainer and TokenFrameContainer.buttons or {}) do
        if call(button.IsVisible,button) then
            data.visible_rows[#data.visible_rows+1]={name=button:GetName(),index=button.index,
                text=button.name and call(button.name.GetText,button.name),
                count=button.count and call(button.count.GetText,button.count)}
        end
    end
    for index=1,3 do
        local name,count,icon,id=call(GetBackpackCurrencyInfo,index)
        local f=_G['BackpackTokenFrameToken'..index]
        if name then data.backpack[#data.backpack+1]={index=index,name=name,count=count,id=id,icon=icon,
            visible=f and not not call(f.IsVisible,f) or false,
            rendered_count=f and f.count and call(f.count.GetText,f.count)} end
    end
    return data
end
