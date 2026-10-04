-- Public action-bar state and installed bindings; this module sends no input.
local function call(fn,...)
    if type(fn)~='function' then return nil end
    local ok,a,b,c,d,e=pcall(fn,...);if ok then return a,b,c,d,e end
end
function Client442ObserveActionBars()
    local result={page=call(GetActionBarPage),bonus_offset=call(GetBonusBarOffset),
        toggles={call(GetActionBarToggles)},locked=call(GetCVarBool,'lockActionBars'),
        keys={},frames={},actions={},forms={},form=call(GetShapeshiftForm),
        frame_limit={max=call(GetCVar,'maxFPS'),background=call(GetCVar,'maxFPSBk')},
        camera_zoom=call(GetCameraZoom),network={call(GetNetStats)}}
    for _,name in ipairs({'NEXTACTIONPAGE','PREVACTIONPAGE','ACTIONPAGE1','ACTIONPAGE2','ACTIONPAGE3',
        'ACTIONPAGE4','ACTIONPAGE5','ACTIONPAGE6','CAMERAZOOMIN','CAMERAZOOMOUT','NEXTVIEW','PREVVIEW'}) do
        result.keys[name]={call(GetBindingKey,name)}
    end
    for _,name in ipairs({'MainMenuBar','MultiBarBottomLeft','MultiBarBottomRight','MultiBarLeft','MultiBarRight',
        'StanceBarFrame','PetActionBarFrame','OverrideActionBar','ExtraActionBarFrame'}) do
        local frame=_G[name];result.frames[name]=frame and frame:IsVisible() or false
    end
    for _,name in ipairs({'ActionButton1','ActionButton12'}) do
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
