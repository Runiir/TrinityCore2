-- 60895 ships Classic guild permission XML with six tabs while its Lua loops
-- over Cataclysm's eight. Supply the missing stock-template widgets. This addon
-- does not issue gameplay commands or bypass server guild permissions.
if tonumber((select(2,GetBuildInfo())))~=60895 then return end
Client442CompatibilityStatus={version=1,guild_tabs_repaired=false}
local function repairGuildTabs()
    local parent=GuildControlPopupFrameTabPermissions
    local sixth=GuildBankTabPermissionsTab6
    if not parent or not sixth then return end
    local created=false
    for i=7,8 do
        local name='GuildBankTabPermissionsTab'..i
        if not _G[name] then
            local tab=CreateFrame('Button',name,parent,'GuildBankTabPermissionsTabTemplate')
            tab:SetID(i);tab:SetText(tostring(i));tab:Hide();created=true
        end
    end
    if created then
        GuildBankTabPermissionsTab8:ClearAllPoints()
        GuildBankTabPermissionsTab8:SetPoint('TOPRIGHT',parent,'TOPRIGHT',-4,27)
        for i=6,7 do
            _G['GuildBankTabPermissionsTab'..i]:ClearAllPoints()
            _G['GuildBankTabPermissionsTab'..i]:SetPoint('RIGHT',_G['GuildBankTabPermissionsTab'..(i+1)],'LEFT',4,0)
        end
    end
    Client442CompatibilityStatus.guild_tabs_repaired=created or Client442CompatibilityStatus.guild_tabs_repaired
    Client442CompatibilityStatus.guild_tab_count=8
end
local events=CreateFrame('Frame')
events:RegisterEvent('ADDON_LOADED');events:RegisterEvent('PLAYER_LOGIN')
events:SetScript('OnEvent',repairGuildTabs)
repairGuildTabs()
