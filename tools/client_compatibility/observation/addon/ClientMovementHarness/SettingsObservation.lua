-- Read visible stock settings and public values. Never invokes setters.
local function call(fn,...)
    if type(fn)~='function' then return nil end
    local ok,a=pcall(fn,...);if ok then return a end
end
function Client442ObserveSettings()
    local panel=SettingsPanel
    local category=panel and call(panel.GetCurrentCategory,panel)
    local search=panel and panel.SearchBox
    local result={visible=panel and panel:IsVisible() or false,
        category=category and {name=call(category.GetName,category),id=call(category.GetID,category)},
        search=search and call(search.GetText,search),
        unapplied=panel and call(panel.HasUnappliedSettings,panel),cvars={},values={},discard_dialogs={},
        interact_keys={primary='',secondary='',known=false}}
    for i=1,3 do
        local popup=_G['StaticPopup'..i]
        if popup and popup:IsVisible() and popup.which=='GAME_SETTINGS_CONFIRM_DISCARD' then
            result.discard_dialogs[#result.discard_dialogs+1]={name=popup:GetName(),which=popup.which}
        end
    end
    if type(GetBindingKey)=='function' then
        local ok,a,b=pcall(GetBindingKey,'INTERACTTARGET')
        if ok then result.interact_keys.primary=a or '';result.interact_keys.secondary=b or '' end
    end
    if type(GetNumBindings)=='function' and type(GetBinding)=='function' then
        for i=1,GetNumBindings() do
            if call(GetBinding,i)=='INTERACTTARGET' then result.interact_keys.known=true;break end
        end
    end
    result.move_pad_visible=MovePadFrame and MovePadFrame:IsVisible() or false
    for _,name in ipairs({'autoLootDefault','lockActionBars','Sound_EnableAllSound','Sound_MasterVolume',
        'Sound_MusicVolume','Sound_SFXVolume','Sound_EnableMusic','cameraTerrainTilt','cameraBobbing',
        'enableMouseSpeed','mouseSpeed','PROXY_MOUSE_LOOK_SPEED','cameraYawMoveSpeed','cameraPitchMoveSpeed',
        'colorblindMode','colorblindSimulator',
        'enableMovePad','PROXY_ENABLE_INTERACT','softTargetInteract','softTargettingInteractKeySound','interactOnLeftClick',
        'RenderScale','gxWindow','gxMaximize','gxMonitor','gxResolution','graphicsQuality','groundEffectDensity','farclip',
        'PROXY_RESOLUTION_RENDER_SCALE','PROXY_RESOLUTION','PROXY_DISPLAY_MODE','PROXY_PRIMARY_MONITOR',
        'showTutorials','nameplateShowEnemies','enableFloatingCombatText','alwaysShowActionBars',
        'PROXY_SHOW_ACTIONBAR_2','PROXY_SHOW_ACTIONBAR_3','PROXY_SHOW_ACTIONBAR_4','PROXY_SHOW_ACTIONBAR_5'}) do
        result.cvars[name]=call(GetCVar,name)
        result.values[name]=Settings and call(Settings.GetValue,name)
    end
    return result
end
