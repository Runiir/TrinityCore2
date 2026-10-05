-- Read only the two owned addons through the pinned build60895 getter API.
local function call(fn,...)
    if type(fn)~='function' then return nil end
    local ok,a,b,c=pcall(fn,...);if ok then return a,b,c end
end
function Client442ObserveAddOns()
    local api=C_AddOns or {}
    local result={visible=AddonList and AddonList:IsVisible() or false,
        count=call(api.GetNumAddOns),version_check=call(api.IsAddonVersionCheckEnabled),rows={}}
    for _,name in ipairs({'ClientMovementHarness','Client442Compatibility'}) do
        local actual,title=call(api.GetAddOnInfo,name)
        local loading,loaded=call(api.IsAddOnLoaded,name)
        result.rows[name]={name=actual,title=title,
            enable_all=call(api.GetAddOnEnableState,name,'0'),
            enable_character=call(api.GetAddOnEnableState,name,UnitName('player')),
            loaded_or_loading=loading,loaded=loaded,
            version=call(api.GetAddOnMetadata,name,'Version')}
    end
    return result
end
