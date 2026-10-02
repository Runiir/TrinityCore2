-- Observe the 60895 Classic guild XML mismatch without modifying stock globals.
-- Creating missing named widgets taints the stock guild initialization path and
-- blocks GuildControlSetRank. The six-versus-eight-tab resource mismatch remains.
if tonumber((select(2,GetBuildInfo())))~=60895 then return end
Client442CompatibilityStatus={version=2,guild_tabs_repaired=false}
local function inspectGuildTabs()
    if not GuildControlPopupFrameTabPermissions then return end
    local count=0
    for i=1,8 do
        if _G['GuildBankTabPermissionsTab'..i] then count=count+1 end
    end
    Client442CompatibilityStatus.guild_tab_count=count
    Client442CompatibilityStatus.guild_tabs_missing=8-count
end
local events=CreateFrame('Frame')
events:RegisterEvent('ADDON_LOADED');events:RegisterEvent('PLAYER_LOGIN')
events:SetScript('OnEvent',inspectGuildTabs)
inspectGuildTabs()
