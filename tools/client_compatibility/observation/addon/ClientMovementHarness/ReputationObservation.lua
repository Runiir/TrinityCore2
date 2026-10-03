-- Paged public faction and stock reputation-control reads; no UI mutations.
local function call(fn,...)
    if type(fn)~='function' then return nil end
    local ok,a,b,c,d,e,f,g,h,i,j,k,l,m,n,o,p=pcall(fn,...)
    if ok then return a,b,c,d,e,f,g,h,i,j,k,l,m,n,o,p end
end
local function faction(index)
    local name,description,reaction,min,max,value,war,toggle,header,collapsed,hasRep,watched,child,id=call(GetFactionInfo,index)
    if not name then return nil end
    return {index=index,id=id,name=name,reaction=reaction,min=min,max=max,value=value,
        at_war=not not war,can_toggle_at_war=not not toggle,header=not not header,
        collapsed=not not collapsed,has_rep=not not hasRep,watched=not not watched,child=not not child,
        inactive=not not call(IsFactionInactive,index),description=tostring(description or ''):sub(1,180)}
end
function Client442ObserveReputation(page)
    local count=call(GetNumFactions) or 0
    local data={count=count,page=page,rows={},selected_index=call(GetSelectedFaction),controls={}}
    for index=(page-1)*8+1,math.min(page*8,count) do
        local row=faction(index);if row then data.rows[#data.rows+1]=row end
    end
    if data.selected_index and data.selected_index>0 then data.selected=faction(data.selected_index) end
    local name,reaction,min,max,value,id=call(GetWatchedFactionInfo)
    data.watched={name=name,reaction=reaction,min=min,max=max,value=value,id=id}
    for _,key in ipairs({'ReputationDetailFrame','ReputationDetailAtWarCheckbox',
        'ReputationDetailInactiveCheckbox','ReputationDetailMainScreenCheckbox','ReputationWatchBar'}) do
        local f=_G[key]
        if f then data.controls[#data.controls+1]={name=key,visible=not not call(f.IsVisible,f),
            enabled=call(f.IsEnabled,f),checked=f.GetChecked and not not call(f.GetChecked,f) or false} end
    end
    local bar=ReputationWatchBar and ReputationWatchBar.StatusBar
    if bar then local low,high=call(bar.GetMinMaxValues,bar)
        data.watch_bar={min=low,max=high,value=call(bar.GetValue,bar),
            text=ReputationWatchBar.OverlayFrame and call(ReputationWatchBar.OverlayFrame.Text.GetText,
                ReputationWatchBar.OverlayFrame.Text)} end
    return data
end
