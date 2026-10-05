-- Read only the two owned addons through the pinned build60895 getter API.
local function call(fn,...)
    if type(fn)~='function' then return nil end
    local ok,a,b,c=pcall(fn,...);if ok then return a,b,c end
end
local clickEvents,watched,clickSerial={},setmetatable({},{__mode='k'}),0
local preferenceCalls,apiWatched,callSerial={},{},0
local function watchPreferenceCalls()
    if type(hooksecurefunc)~='function' then return end
    local api=C_AddOns or {}
    for _,binding in ipairs({{api,'C_AddOns.EnableAddOn','EnableAddOn'},
        {api,'C_AddOns.DisableAddOn','DisableAddOn'},{_G,'EnableAddOn','EnableAddOn'},
        {_G,'DisableAddOn','DisableAddOn'}}) do
        local owner,label,method=binding[1],binding[2],binding[3]
        if type(owner[method])=='function' and not apiWatched[label] then
            apiWatched[label]=true
            hooksecurefunc(owner,method,function(name,character)
                callSerial=callSerial+1
                local known=call(api.GetAddOnInfo,name)
                local allowed=known=='Client442Compatibility' or known=='ClientMovementHarness'
                local requested=(type(name)=='number' or name=='Client442Compatibility' or
                    name=='ClientMovementHarness' or name=='Client442 Compatibility') and name or nil
                preferenceCalls[#preferenceCalls+1]={serial=callSerial,method=label,name_type=type(name),
                    requested=requested,owned_name=allowed and known or nil,
                    character_type=type(character),character=(character=='0' or character==0 or character=='All' or
                        character==UnitName('player')) and character or nil,
                    enable_all=allowed and call(api.GetAddOnEnableState,known,'0') or nil}
                if #preferenceCalls>8 then table.remove(preferenceCalls,1) end
            end)
        end
    end
end
local function watchClicks()
    local button=AddonListEntry2Enabled
    if button and not watched[button] and type(button.HookScript)=='function' then
        watched[button]=true
        button:HookScript('OnClick',function(self,mouseButton,down)
            clickSerial=clickSerial+1
            clickEvents[#clickEvents+1]={serial=clickSerial,name=self:GetName(),button=mouseButton,
                down_known=type(down)=='boolean',down=down,checked=call(self.GetChecked,self),
                shift=call(IsShiftKeyDown),control=call(IsControlKeyDown),alt=call(IsAltKeyDown),
                enable_all=call(C_AddOns and C_AddOns.GetAddOnEnableState,'Client442Compatibility','0')}
            if #clickEvents>8 then table.remove(clickEvents,1) end
        end)
    end
end
function Client442ObserveAddOnClicks()
    return {events=clickEvents,hook_installed=AddonListEntry2Enabled and watched[AddonListEntry2Enabled] or false,
        preference_calls=preferenceCalls,api_hooks=apiWatched}
end
function Client442ObserveAddOns()
    watchPreferenceCalls()
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
