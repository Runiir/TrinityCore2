-- Read visible stock settings and public values. Never invokes setters.
local function call(fn,...)
    if type(fn)~='function' then return nil end
    local ok,a=pcall(fn,...);if ok then return a end
end
local graphicsSettings={
    {'graphicsQuality','PROXY_GRAPHICS_QUALITY'},
    {'graphicsShadowQuality','PROXY_SHADOW_QUALITY'},
    {'graphicsLiquidDetail','PROXY_LIQUID_DETAIL'},
    {'graphicsParticleDensity','PROXY_PARTICLE_DENSITY'},
    {'graphicsSSAO','PROXY_SSAO'},
    {'graphicsTextureResolution','PROXY_TEXTURE_RESOLUTION'},
    {'graphicsSpellDensity','PROXY_SPELL_DENSITY'},
    {'graphicsProjectedTextures','PROXY_PROJECTED_TEXTURES'},
    {'graphicsEnvironmentDetail','PROXY_ENVIRONMENT_DETAIL'},
    {'graphicsGroundClutter','PROXY_GROUND_CLUTTER'},
    {'graphicsSunshafts','PROXY_SUNSHAFTS'},
}
function Client442ObserveAdvancedQualityControl(frame)
    local section=frame
    for level=1,8 do
        if not section then return nil end
        local initializer=call(section.GetElementData,section)
        local data=type(initializer)=='table' and initializer.data
        if type(data)=='table' then
            for _,role in ipairs({'base','raid'}) do
                local container=role=='base' and section.BaseQualityControls or section.RaidQualityControls
                local quality=container and container.GraphicsQuality
                local steppers=quality and quality.SliderWithSteppers
                local settings=role=='base' and data.settings or data.raidSettings
                local setting=settings and settings[role=='base' and 'graphicsQuality' or 'raidGraphicsQuality']
                if steppers and setting then
                    for _,key in ipairs({'Slider','Back','Forward'}) do
                        if frame==steppers[key] then
                            local variable=call(setting.GetVariable,setting)
                            local expected=role=='base' and 'PROXY_GRAPHICS_QUALITY' or 'PROXY_RAID_GRAPHICS_QUALITY'
                            if variable~=expected then return nil end
                            return {variable=variable,value=call(setting.GetValue,setting),
                                name=call(setting.GetName,setting),role=role,control=key}
                        end
                    end
                end
            end
        end
        section=call(section.GetParent,section)
    end
end
function Client442ShouldObserveSettings(panel,tick)
    return panel and (panel:IsVisible() or tick%10==0) or false
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
    result.lower_graphics_values={}
    local lowerQuality=tonumber(Settings and call(Settings.GetValue,'PROXY_GRAPHICS_QUALITY'))
    if lowerQuality and lowerQuality>0 and lowerQuality<=9 then lowerQuality=lowerQuality-1 else lowerQuality=nil end
    result.lower_graphics_quality=lowerQuality
    for _,pair in ipairs(graphicsSettings) do
        result.cvars[pair[1]]=call(GetCVar,pair[1])
        result.values[pair[2]]=Settings and call(Settings.GetValue,pair[2])
        if lowerQuality and pair[1]~='graphicsQuality' then
            local value=call(GetGraphicsCVarValueForQualityLevel,pair[1],lowerQuality,false)
            if type(value)=='number' then
                result.lower_graphics_values[pair[2]]=math.max(pair[1]=='graphicsParticleDensity' and 1 or -1,value)
            end
        end
    end
    return result
end
