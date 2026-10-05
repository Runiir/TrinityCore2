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
        unapplied=panel and call(panel.HasUnappliedSettings,panel),cvars={},values={}}
    for _,name in ipairs({'autoLootDefault','lockActionBars','Sound_EnableAllSound','Sound_MasterVolume',
        'Sound_MusicVolume','Sound_SFXVolume','Sound_EnableMusic','cameraTerrainTilt','cameraBobbing',
        'enableMouseSpeed','mouseSpeed','PROXY_MOUSE_LOOK_SPEED','cameraYawMoveSpeed','cameraPitchMoveSpeed',
        'colorblindMode','colorblindSimulator',
        'showTutorials','nameplateShowEnemies','enableFloatingCombatText','alwaysShowActionBars',
        'PROXY_SHOW_ACTIONBAR_2','PROXY_SHOW_ACTIONBAR_3','PROXY_SHOW_ACTIONBAR_4','PROXY_SHOW_ACTIONBAR_5'}) do
        result.cvars[name]=call(GetCVar,name)
        result.values[name]=Settings and call(Settings.GetValue,name)
    end
    return result
end
