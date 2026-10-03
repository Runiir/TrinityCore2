-- Public stock equipment-set state. No setters or gameplay API calls.
local function read(fn,...)
    if type(fn)~='function' then return nil end
    local ok,a,b,c,d,e,f,g,h,i=pcall(fn,...)
    if ok then return a,b,c,d,e,f,g,h,i end
end
function Client442ObserveEquipment()
    local api=C_EquipmentSet or {}
    local ids=read(api.GetEquipmentSetIDs) or {}
    local rows={}
    for _,id in ipairs(ids) do
        if #rows>=20 then break end
        local name,icon,setID,equipped,total,worn,stored,lost,ignored=read(api.GetEquipmentSetInfo,id)
        rows[#rows+1]={id=id,name=name,icon=icon,set_id=setID,equipped=equipped,
            total=total,worn=worn,stored=stored,lost=lost,ignored=ignored,
            spec=read(api.GetEquipmentSetAssignedSpec,id)}
    end
    local pane=PaperDollFrame and PaperDollFrame.EquipmentManagerPane
    return {count=read(api.GetNumEquipmentSets),sets=rows,
        manager_visible=pane and not not read(pane.IsVisible,pane) or false,
        selected=pane and pane.selectedSetID,
        popup_visible=GearManagerPopupFrame and not not read(GearManagerPopupFrame.IsVisible,GearManagerPopupFrame) or false,
        helm=read(IsHelmShowing),cloak=read(IsCloakShowing)}
end
