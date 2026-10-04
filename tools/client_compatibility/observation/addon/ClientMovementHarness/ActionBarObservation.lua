-- Public action-bar state and installed bindings; this module sends no input.
local function call(fn,...)
    if type(fn)~='function' then return nil end
    local ok,a,b,c,d,e=pcall(fn,...);if ok then return a,b,c,d,e end
end
function Client442ObserveActionBars()
    Client442HookPerformanceTooltip()
    local result={page=call(GetActionBarPage),bonus_offset=call(GetBonusBarOffset),
        toggles={call(GetActionBarToggles)},locked=call(GetCVarBool,'lockActionBars'),
        keys={},frames={},actions={},forms={},form=call(GetShapeshiftForm),
        active_spec=call(GetActiveTalentGroup),viewable_pages={},
        effective_page=MainMenuBarArtFrame and call(MainMenuBarArtFrame.GetAttribute,MainMenuBarArtFrame,'actionpage'),
        frame_limit={max=call(GetCVar,'maxFPS'),background=call(GetCVar,'maxFPSBk')},
        camera_zoom=call(GetCameraZoom),network={call(GetNetStats)},
        performance_event=Client442PerformanceTooltipEvent()}
    for index=1,6 do
        if VIEWABLE_ACTION_BAR_PAGES and VIEWABLE_ACTION_BAR_PAGES[index] then
            result.viewable_pages[#result.viewable_pages+1]=index
        end
    end
    for _,name in ipairs({'NEXTACTIONPAGE','PREVIOUSACTIONPAGE','ACTIONPAGE1','ACTIONPAGE2','ACTIONPAGE3',
        'ACTIONPAGE4','ACTIONPAGE5','ACTIONPAGE6','CAMERAZOOMIN','CAMERAZOOMOUT','NEXTVIEW','PREVVIEW'}) do
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
        result.forms[#result.forms+1]={index=index,active=active,castable=castable,spell=spell,
            button='StanceButton'..index}
    end
    return result
end
