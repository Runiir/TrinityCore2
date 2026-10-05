-- Public minimap geometry, displayed saved pins and normal tooltip text.
-- Native tracking blips have no public object-position list. The host checks
-- their tooltip before treating a blip as a live archaeology find.
local function call(fn,...)
    if type(fn)~='function' then return end
    local ok,a,b,c,d,e,f=pcall(fn,...)
    if ok then return a,b,c,d,e,f end
end
local function clean(value)
    return type(value)=='string' and value:gsub('|c%x%x%x%x%x%x%x%x',''):gsub('|r',''):sub(1,160) or nil
end
function WhitemaneLiveMinimap()
    if not Minimap or not Minimap:IsVisible() then return {visible=false} end
    local scale=Minimap:GetEffectiveScale()
    local screenScale=UIParent:GetEffectiveScale()
    local sw,sh=GetScreenWidth()*screenScale,GetScreenHeight()*screenScale
    local x,y=Minimap:GetCenter()
    local zoom=Minimap:GetZoom()
    local outdoor=tonumber(call(GetCVar,'minimapZoom'))==zoom
    local sizes=outdoor and {466+2/3,400,333+1/3,266+2/6,200,133+1/3} or {300,240,180,120,80,50}
    local radius=call(C_Minimap and C_Minimap.GetViewRadius) or sizes[zoom+1]/2
    local row={visible=true,x=x*scale/sw,y=1-y*scale/sh,
        width=Minimap:GetWidth()*scale/sw,height=Minimap:GetHeight()*scale/sh,
        radius_yards=radius,zoom=zoom,rotating=call(GetCVar,'rotateMinimap')=='1',
        facing=call(GetPlayerFacing),shape=call(GetMinimapShape) or 'ROUND',saved_pins={},tooltip_lines={}}
    for i=1,math.min(call(C_Minimap and C_Minimap.GetNumTrackingTypes or GetNumTrackingTypes) or 0,64) do
        local info,_,active=call(C_Minimap and C_Minimap.GetTrackingInfo or GetTrackingInfo,i)
        local name=type(info)=='table' and info.name or info
        if type(name)=='string' and name:lower():find('archaeology',1,true) then
            row.artifact_tracking=type(info)=='table' and not not info.active or not not active
        end
    end
    for _,pin in ipairs({Minimap:GetChildren()}) do
        if pin.nodeType=='Archaeology' and pin:IsShown() and pin:GetAlpha()>0 then
            local px,py=pin:GetCenter()
            local ps=pin:GetEffectiveScale()
            if px and py then row.saved_pins[#row.saved_pins+1]={x=px*ps/sw,y=1-py*ps/sh,marker_id=pin.coords} end
            if #row.saved_pins>=32 then break end
        end
    end
    for _,tip in ipairs({GameTooltip,MinimapTooltip}) do
        if tip:IsShown() then
            local name=tip:GetName()
            local owner=call(tip.GetOwner,tip)
            if owner==Minimap or tip==MinimapTooltip then
                for i=1,math.min(call(tip.NumLines,tip) or 0,12) do
                    local label=_G[name..'TextLeft'..i]
                    local text=label and clean(label:GetText())
                    if text then row.tooltip_lines[#row.tooltip_lines+1]=text end
                end
            end
        end
    end
    return row
end
