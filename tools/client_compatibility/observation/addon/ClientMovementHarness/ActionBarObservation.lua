-- Public action-bar state and installed bindings; this module sends no input.
local function call(fn,...)
    if type(fn)~='function' then return nil end
    local ok,a,b,c,d,e=pcall(fn,...);if ok then return a,b,c,d,e end
end
local mouseHistory,mousePrevious,mouseElapsed={},nil,0
local function mouseState()
    local focus=call(GetMouseFoci)
    if type(focus)~='table' then focus={call(GetMouseFocus)} end
    local names={}
    for index=1,math.min(#focus,4) do
        local object=focus[index]
        names[index]=call(object.GetName,object) or call(object.GetObjectType,object) or 'unnamed'
    end
    return {focus=names,mouseover_guid=call(UnitGUID,'mouseover'),mouseover_name=call(UnitName,'mouseover'),
        left=call(IsMouseButtonDown,'LeftButton'),right=call(IsMouseButtonDown,'RightButton'),
        middle=call(IsMouseButtonDown,'MiddleButton'),
        button2_action=call(GetBindingAction,'BUTTON2'),button2_override=call(GetBindingAction,'BUTTON2',true),
        api={mouse_foci=type(GetMouseFoci)=='function',mouse_focus=type(GetMouseFocus)=='function',
            mouse_button=type(IsMouseButtonDown)=='function'}}
end
local mouseFrame=CreateFrame('Frame')
mouseFrame:SetScript('OnUpdate',function(_,delta)
    mouseElapsed=mouseElapsed+delta;if mouseElapsed<.25 then return end;mouseElapsed=0
    local current=mouseState()
    local identity=table.concat(current.focus,',')..'|'..tostring(current.mouseover_guid)..'|'..
        tostring(current.left)..'|'..tostring(current.right)..'|'..tostring(current.middle)
    if identity~=mousePrevious then
        mousePrevious=identity;current.time=GetTime();mouseHistory[#mouseHistory+1]=current
        if #mouseHistory>8 then table.remove(mouseHistory,1) end
    end
end)
function Client442ObserveActionBars()
    Client442HookPerformanceTooltip()
    local rootScale=UIParent and call(UIParent.GetEffectiveScale,UIParent)
    local screenWidth,screenHeight=call(GetScreenWidth),call(GetScreenHeight)
    local width=rootScale and screenWidth and rootScale*screenWidth
    local height=rootScale and screenHeight and rootScale*screenHeight
    local result={page=call(GetActionBarPage),bonus_offset=call(GetBonusBarOffset),
        toggles={call(GetActionBarToggles)},locked=call(GetCVarBool,'lockActionBars'),
        keys={},frames={},actions={},forms={},form=call(GetShapeshiftForm),
        active_spec=call(GetActiveTalentGroup),viewable_pages={},
        effective_page=MainMenuBarArtFrame and call(MainMenuBarArtFrame.GetAttribute,MainMenuBarArtFrame,'actionpage'),
        frame_limit={max=call(GetCVar,'maxFPS'),background=call(GetCVar,'maxFPSBk')},
        camera_zoom=call(GetCameraZoom),network={call(GetNetStats)},
        power=call(UnitPower,'player'),power_type=call(UnitPowerType,'player'),
        pose={sheath=call(GetSheathState),speed=call(GetUnitSpeed,'player')},
        viewport={width=width,height=height,basis='scaled_game_ui_screen'},
        performance_event=Client442PerformanceTooltipEvent(),mouse=mouseState(),mouse_history=mouseHistory}
    for index=1,6 do
        if VIEWABLE_ACTION_BAR_PAGES and VIEWABLE_ACTION_BAR_PAGES[index] then
            result.viewable_pages[#result.viewable_pages+1]=index
        end
    end
    for _,name in ipairs({'NEXTACTIONPAGE','PREVIOUSACTIONPAGE','ACTIONPAGE1','ACTIONPAGE2','ACTIONPAGE3',
        'ACTIONPAGE4','ACTIONPAGE5','ACTIONPAGE6','CAMERAZOOMIN','CAMERAZOOMOUT','NEXTVIEW','PREVVIEW',
        'SITORSTAND','TOGGLESHEATH','MOVEFORWARD','MOVEBACKWARD','TURNLEFT','TURNRIGHT',
        'STRAFELEFT','STRAFERIGHT','TOGGLEAUTORUN','TOGGLERUN','JUMP',
        'TARGETSELF','TARGETPARTYMEMBER1','TARGETLASTTARGET','ASSISTTARGET',
        'TARGETNEARESTENEMY','TARGETPREVIOUSENEMY','TARGETNEARESTFRIEND',
        'TARGETFOCUS','FOCUSTARGET','TARGETTARGET','REPLY','REPLY2',
        'INTERACTTARGET','INTERACTMOUSEOVER','CAMERAORSELECTORMOVE','TURNORACTION'}) do
        result.keys[name]={call(GetBindingKey,name)}
    end
    for _,name in ipairs({'MainMenuBar','MultiBarBottomLeft','MultiBarBottomRight','MultiBarLeft','MultiBarRight',
        'StanceBarFrame','PetActionBarFrame','OverrideActionBar','ExtraActionBarFrame'}) do
        local frame=_G[name];result.frames[name]=frame and frame:IsVisible() or false
    end
    for index=1,12 do
        local name='ActionButton'..index
        local button=_G[name]
        if button then
            local kind,id=call(GetActionInfo,button.action)
            local start,duration,enabled=call(GetActionCooldown,button.action)
            result.actions[#result.actions+1]={button=name,slot=button.action,kind=kind,id=id,
                visible=button:IsVisible(),cooldown={start=start,duration=duration,enabled=enabled}}
        end
    end
    for index=1,math.min(tonumber(call(GetNumShapeshiftForms)) or 0,4) do
        local icon,active,castable,spell=call(GetShapeshiftFormInfo,index)
        local name='StanceButton'..index
        local button=_G[name]
        local row={index=index,active=active,castable=castable,spell=spell,button=name}
        if button then
            row.visible=call(button.IsVisible,button)
            row.checked=call(button.GetChecked,button)
            row.enabled=call(button.IsEnabled,button)
            local x,y=call(button.GetCenter,button)
            local scale=call(button.GetEffectiveScale,button)
            if x and y and scale and width and height and width>0 and height>0 then
                row.x=math.floor(x*scale/width*65535)
                row.y=math.floor((1-y*scale/height)*65535)
            end
        end
        result.forms[#result.forms+1]=row
    end
    return result
end
