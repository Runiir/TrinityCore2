-- Read only the two owned addons through the pinned build60895 getter API.
local function call(fn,...)
    if type(fn)~='function' then return nil end
    local ok,a,b,c=pcall(fn,...);if ok then return a,b,c end
end
local clickEvents,watched,clickSerial={},setmetatable({},{__mode='k'}),0
local function watchClicks()
    local button=AddonListEntry2Enabled
    if button and not watched[button] and type(button.HookScript)=='function' then
        watched[button]=true
        button:HookScript('OnClick',function(self,mouseButton,down)
            clickSerial=clickSerial+1
            clickEvents[#clickEvents+1]={serial=clickSerial,name=self:GetName(),button=mouseButton,
                down_known=type(down)=='boolean',down=down,checked=call(self.GetChecked,self),
                enable_all=call(C_AddOns and C_AddOns.GetAddOnEnableState,'Client442Compatibility','0')}
            if #clickEvents>8 then table.remove(clickEvents,1) end
        end)
    end
end
function Client442ObserveAddOnClicks()
    return {events=clickEvents,hook_installed=AddonListEntry2Enabled and watched[AddonListEntry2Enabled] or false}
end
function Client442ObserveAddOns()
    watchClicks()
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
