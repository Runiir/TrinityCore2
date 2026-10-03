-- Public map APIs and existing stock frame properties. No gameplay mutations.
local function call(f,...)
    if type(f)~='function' then return end
    local ok,a,b,c,d=pcall(f,...);if ok then return a,b,c,d end
end
local function info(id)
    local value=id and call(C_Map and C_Map.GetMapInfo,id)
    if value then return {id=value.mapID,name=value.name,type=value.mapType,parent=value.parentMapID} end
end
local function rect(frame)
    if not frame then return end
    local x,y,w,h=call(frame.GetRect,frame);local scale=call(frame.GetEffectiveScale,frame)
    if not x or not y or not w or not h or not scale then return end
    local width=GetScreenWidth()*UIParent:GetEffectiveScale()
    local height=GetScreenHeight()*UIParent:GetEffectiveScale()
    return {left=x*scale/width,top=1-(y+h)*scale/height,width=w*scale/width,height=h*scale/height}
end
local function pins(map,template)
    local rows={};if not map then return rows end
    local iterator,state,initial=call(map.EnumeratePinsByTemplate,map,template)
    if type(iterator)~='function' then return rows end
    for pin in iterator,state,initial do
        if #rows>=16 then break end
        local value=pin.digSiteInfo or pin.poiInfo or {}
        rows[#rows+1]={template=template,visible=not not call(pin.IsVisible,pin),
            research_site=value.researchSiteID,blob=value.poiBlobID,name=value.name or pin.name,
            rect=rect(pin)}
    end
    return rows
end
local function button(frame)
    if not frame then return end
    return {visible=not not call(frame.IsVisible,frame),enabled=not not call(frame.IsEnabled,frame),rect=rect(frame)}
end
function Client442ObserveMap()
    local map=WorldMapFrame;local id=map and call(map.GetMapID,map)
    local best=call(C_Map and C_Map.GetBestMapForUnit,'player')
    local pos=id and call(C_Map and C_Map.GetPlayerMapPosition,id,'player')
    local x,y=pos and call(pos.GetXY,pos)
    -- Lua's logical operators collapse multiple returns; read the second
    -- coordinate explicitly from the public vector.
    if pos then x,y=call(pos.GetXY,pos) end
    local meta=info(id);local sites={}
    for _,value in ipairs(id and call(C_ResearchInfo and C_ResearchInfo.GetDigSitesForMap,id) or {}) do
        if #sites>=16 then break end
        sites[#sites+1]={id=value.researchSiteID,blob=value.poiBlobID,name=value.name,x=value.position and value.position.x,
            y=value.position and value.position.y}
    end
    local check=WorldMapShowDigsites
    return {visible=map and not not call(map.IsVisible,map) or false,id=id,info=meta,
        parent=meta and info(meta.parent),best=info(best),player=pos and {x=x,y=y},
        world_position={call(UnitPosition,'player')},binding_keys={call(GetBindingKey,'TOGGLEWORLDMAP')},
        canvas=map and rect(call(map.GetCanvas,map)),canvas_scale=map and call(map.GetCanvasScale,map),
        digsites_enabled=not not call(GetCVarBool,'digSites'),digsite_checkbox=check and not not call(check.GetChecked,check),
        sites=sites,icon_pins=pins(map,'DigSitePinTemplate'),blob_pins=pins(map,'DigSiteBlobPinTemplate'),
        minimap_zoom=Minimap and call(Minimap.GetZoom,Minimap),
        minimap_zoom_levels=Minimap and call(Minimap.GetZoomLevels,Minimap),
        minimap_buttons={zoom_in=button(MinimapZoomIn),zoom_out=button(MinimapZoomOut)}}
end
