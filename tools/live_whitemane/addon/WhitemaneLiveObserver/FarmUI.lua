-- Public UI/route reads only. No selection, casts, interactions or movement.
local capacity, columns, cell = 16384, 128, 3
local panel = CreateFrame("Frame", "WhitemaneLiveFarmUI", UIParent)
panel:SetScale(1 / UIParent:GetEffectiveScale())
panel:SetSize(columns*cell, math.ceil((capacity+12)/(3*columns))*cell)
panel:SetPoint("TOPLEFT", UIParent, "TOPLEFT", 340, -16)
panel:SetFrameStrata("TOOLTIP"); panel:SetFrameLevel(10000); panel:EnableMouse(false)
local pixels, previous = {}, {}
for i=1,math.ceil((capacity+12)/3) do
    local pixel=panel:CreateTexture(nil,"OVERLAY"); pixel:SetSize(cell,cell)
    pixel:SetPoint("TOPLEFT",panel,"TOPLEFT",((i-1)%columns)*cell,-math.floor((i-1)/columns)*cell)
    pixels[i]=pixel
end
local function call(fn,...)
    if type(fn)~="function" then return end
    local ok,a,b,c,d,e,f,g,h,i,j=pcall(fn,...)
    if ok then return a,b,c,d,e,f,g,h,i,j end
end
local function visible(frame) return frame and not not call(frame.IsVisible,frame) end
local function clean(text)
    return type(text)=="string" and text:gsub("|c%x%x%x%x%x%x%x%x",""):gsub("|r",""):sub(1,160) or nil
end
local function text(frame) return frame and clean(call(frame.GetText,frame)) end
local function control(frame,label,extra)
    if not visible(frame) then return end
    local x,y=call(frame.GetCenter,frame)
    local scale=call(frame.GetEffectiveScale,frame)
    local width,height=GetScreenWidth()*UIParent:GetEffectiveScale(),GetScreenHeight()*UIParent:GetEffectiveScale()
    if not x or not y or not scale or width<=0 or height<=0 then return end
    local row={name=call(frame.GetName,frame),label=clean(label) or "",x=x*scale/width,y=1-y*scale/height,
               enabled=not frame.IsEnabled or not not call(frame.IsEnabled,frame)}
    for key,value in pairs(extra or {}) do row[key]=value end
    return row
end
local function append(rows,row) if row then rows[#rows+1]=row end end
local function actionbars()
    local rows={}
    for _,prefix in ipairs({"ActionButton","MultiBarBottomLeftButton","MultiBarBottomRightButton","MultiBarLeftButton","MultiBarRightButton"}) do
        for index=1,12 do
            local frame=_G[prefix..index]
            local slot=frame and (frame.action or call(frame.GetAttribute,frame,"action"))
            local kind,id
            if slot then kind,id=call(GetActionInfo,slot) end
            if kind=="flyout" then
                local label=call(GetFlyoutInfo,id)
                append(rows,control(frame,label,{kind=kind,id=id,slot=slot}))
            elseif kind=="spell" then
                local label=call(C_Spell and C_Spell.GetSpellName or GetSpellInfo,id)
                if id==5000028 or id==88342 or id==88344 or
                    (label and label:lower():find("tol barad",1,true)) or
                    call(frame.GetName,frame)=="MultiBarLeftButton2" then
                    append(rows,control(frame,label,{kind=kind,id=id,slot=slot}))
                end
            elseif kind and call(frame.GetName,frame)=="MultiBarLeftButton2" then
                append(rows,control(frame,call(GetActionText,slot),{kind=kind,id=id,slot=slot}))
            end
        end
    end
    return rows
end
local function flyout()
    local rows={}
    if visible(SpellFlyout) then
        for index=1,32 do
            local frame=_G["SpellFlyoutPopupButton"..index]
            if not frame then break end
            local id=frame.spellID
            local label=id and call(C_Spell and C_Spell.GetSpellName or GetSpellInfo,id) or frame.spellName
            append(rows,control(frame,label,{kind="spell",id=id}))
        end
    end
    return rows
end
local function journal()
    local frame=ArchaeologyFrame
    local artifact=frame and frame.artifactPage
    local summary=frame and frame.summaryPage
    local solve=artifact and artifact.solveFrame
    local result={visible=not not visible(frame),artifact_visible=not not visible(artifact),
        summary_visible=not not visible(summary),race=artifact and artifact.raceID,races={},keystones={},controls={}}
    if not result.visible then return result end
    local name,_,_,_,_,sockets,_,spell=call(GetSelectedArtifactInfo)
    local base,adjust,cost=call(GetArtifactProgress)
    result.project={name=clean(name),spell=spell,sockets=sockets,base=base,adjust=adjust,cost=cost,
                    can_solve=not not call(CanSolveArtifact)}
    append(result.controls,control(frame.CloseButton or _G.ArchaeologyFrameCloseButton,"Close journal",{kind="close"}))
    append(result.controls,control(frame.summaryButton or _G.ArchaeologyFrameSummaryButton,"Current artifacts",{kind="summary"}))
    if summary then
        local per=ARCHAEOLOGY_MAX_RACES or 12
        for index=1,per do
            local race=index+per*((summary.currentPage or 1)-1)
            local label=call(GetArchaeologyRaceInfo,race,false)
            append(result.races,control(summary["race"..index],label,{race=race}))
        end
        append(result.controls,control(summary.nextPageButton,"Next races",{kind="next"}))
        append(result.controls,control(summary.prevPageButton,"Previous races",{kind="previous"}))
    end
    if solve then
        result.solve=control(solve.solveButton,"Solve current artifact",{kind="solve"})
        for index=1,4 do
            local stone=solve["keystone"..index]
            append(result.keystones,control(stone,stone and stone.tooltip,{index=index,
                added=not not call(ItemAddedToArtifact,index)}))
        end
    end
    return result
end
local function taxi()
    local rows={}
    if visible(TaxiFrame) then
        local map=call(GetTaxiMapID)
        for _,node in ipairs(call(C_TaxiMap and C_TaxiMap.GetAllTaxiNodes,map or 0) or {}) do
            append(rows,control(_G["TaxiButton"..node.slotIndex],node.name or call(TaxiNodeName,node.slotIndex),
                {id=node.nodeID,slot=node.slotIndex,state=node.state}))
        end
    end
    return rows
end
local function canopic()
    local rows={}
    if visible(CanopicHelperFrame) then
        for _,child in ipairs({CanopicHelperFrame:GetChildren()}) do
            local label=call(child.GetText,child)
            if label then append(rows,control(child,label)) end
        end
    end
    return rows
end
local function gossip()
    local rows,options={},{}
    if not visible(GossipFrame) then return rows end
    for _,entry in ipairs(call(C_GossipInfo and C_GossipInfo.GetOptions) or {}) do
        options[clean(entry.name)]=entry.gossipOptionID
    end
    local seen={}
    local function scan(frame,depth)
        if depth>8 or not visible(frame) then return end
        local label=text(frame) or text(frame.Text) or text(frame.text)
        if options[label] and frame.GetObjectType and frame:GetObjectType()=="Button" and not seen[label] then
            append(rows,control(frame,label,{id=options[label]}));seen[label]=true
        end
        if frame.GetRegions then
            for _,region in ipairs({frame:GetRegions()}) do
                local caption=text(region)
                if options[caption] and not seen[caption] then
                    append(rows,control(region,caption,{id=options[caption]}));seen[caption]=true
                end
            end
        end
        if frame.GetChildren then for _,child in ipairs({frame:GetChildren()}) do scan(child,depth+1) end end
    end
    scan(GossipFrame,0)
    return rows
end
local function loot()
    local rows={}
    if not visible(LootFrame) then return rows end
    for index=1,LOOTFRAME_NUMBUTTONS or 4 do
        local button=_G['LootButton'..index]
        append(rows,control(button,text(_G['LootButton'..index..'Text']),{slot=button and button.slot}))
    end
    return rows
end
local function snapshot()
    local tip=text(GameTooltipTextLeft1)
    local x,y=GetCursorPosition()
    local uiScale=UIParent:GetEffectiveScale()
    local keys={}
    for _,name in ipairs({"INTERACTTARGET","TARGETNEARESTENEMY","MOVEFORWARD","TURNLEFT","TURNRIGHT","JUMP","DESCEND","PITCHUP","PITCHDOWN"}) do
        keys[name]={call(GetBindingKey,name)}
    end
    local start,duration,enabled=call(GetSpellCooldown,80451)
    local cooldown=call(C_Spell and C_Spell.GetSpellCooldown,80451)
    if type(cooldown)=='table' then start,duration,enabled=cooldown.startTime,cooldown.duration,cooldown.isEnabled end
    local ends=(start or 0)+(duration or 0)
    return {uptime=GetTime(),route=call(WhitemaneLiveCanopicRoute),actionbars=actionbars(),flyout=flyout(),
        minimap=call(WhitemaneLiveMinimap),survey={ready=enabled~=0 and enabled~=false and ends<=GetTime(),cooldown_ends=ends},
        journal=journal(),taxi=taxi(),gossip=gossip(),loot=loot(),canopic=canopic(),tooltip=visible(GameTooltip) and tip or nil,
        cursor={x=x/(GetScreenWidth()*uiScale),y=1-y/(GetScreenHeight()*uiScale)},
        soft_interact={exists=not not call(UnitExists,"softinteract"),name=call(UnitName,"softinteract"),
                       enabled=call(GetCVar,"SoftTargetInteract")},bindings=keys,
        flyable=not not call(IsFlyableArea),indoors=not not call(IsIndoors),
        auto_loot=call(GetCVar,'autoLootDefault'),recipe_known=not not call(IsPlayerSpell,93328)}
end
local function quote(value)
    return '"'..value:gsub('[%z\1-\31\\"]',function(c)
        if c=='"' or c=='\\' then return '\\'..c end
        return string.format('\\u%04x',c:byte())
    end)..'"'
end
local function json(value)
    local kind=type(value)
    if kind=="nil" then return "null" elseif kind=="boolean" or kind=="number" then return tostring(value)
    elseif kind=="string" then return quote(value) end
    local result={}
    if #value>0 then
        for _,item in ipairs(value) do result[#result+1]=json(item) end
        return "["..table.concat(result,",").."]"
    end
    local keys={};for key in pairs(value) do keys[#keys+1]=key end;table.sort(keys)
    for _,key in ipairs(keys) do result[#result+1]=quote(key)..":"..json(value[key]) end
    return "{"..table.concat(result,",").."}"
end
local function number(bytes,value,width)
    for power=width-1,0,-1 do bytes[#bytes+1]=math.floor(value/256^power)%256 end
end
local sequence,elapsed=0,0
local lastError
panel:RegisterEvent('UI_ERROR_MESSAGE')
panel:SetScript('OnEvent',function(_,_,code,message)lastError={code=code,message=clean(message),at=GetTime()} end)
local function sample()
    sequence=(sequence+1)%4294967296
    local ok,result=pcall(snapshot)
    if ok and WhitemaneLiveActivity then
        local activity=call(WhitemaneLiveActivity)
        for key,value in pairs(activity or {}) do result[key]=value end
    end
    if ok and WhitemaneLiveRelayUI then
        local fast={soft_interact=result.soft_interact,tooltip=result.tooltip,
            camera_zoom=call(GetCameraZoom),error=lastError,auto_loot=call(GetCVar,'autoLootDefault'),
            frame_rate=math.floor((call(GetFramerate) or 0)+.5),
            max_fps=call(GetCVar,'maxFPS'),background_max_fps=call(GetCVar,'maxFPSBk')}
        local cursor=result.cursor
        result.uptime=nil;result.cursor=nil;result.soft_interact=nil;result.tooltip=nil
        WhitemaneLiveRelayUI(json(result),fast,json)
        result.uptime=GetTime();result.cursor=cursor;result.soft_interact=fast.soft_interact;result.tooltip=fast.tooltip
        result.camera_zoom=fast.camera_zoom;result.error=lastError
        result.frame_rate=fast.frame_rate;result.max_fps=fast.max_fps;result.background_max_fps=fast.background_max_fps
        result.relay_status=call(WhitemaneLiveRelayStatus)
    end
    local payload=json(ok and result or {observer_error=tostring(result):sub(1,200)})
    if #payload>capacity then payload=json({observer_error="Farm UI packet capacity exceeded",bytes=#payload}) end
    local bytes={84,67,85,51};number(bytes,#payload,2);number(bytes,sequence,4)
    for i=1,#payload do bytes[#bytes+1]=payload:byte(i) end
    local a,b=0,0;for _,v in ipairs(bytes) do a=(a+v)%255;b=(b+a)%255 end
    number(bytes,b*256+a,2)
    for i=1,math.ceil(#bytes/3) do
        local r,g,b=bytes[(i-1)*3+1] or 0,bytes[(i-1)*3+2] or 0,bytes[(i-1)*3+3] or 0
        local code=r*65536+g*256+b
        if previous[i]~=code then pixels[i]:SetColorTexture(r/255,g/255,b/255,1);previous[i]=code end
    end
end
panel:SetScript("OnUpdate",function(_,delta)
    elapsed=elapsed+delta
    if elapsed>=.2 then elapsed=0;sample() end
end)
