-- The installed SelectMacro(nil) selects slot1 even when the bank is empty.
-- Hide stale details and prevent deletion/editing without a valid macro.
if tonumber((select(2,GetBuildInfo())))~=60895 then return end
local installed=false
local function emptyDetails(frame)
    local tab=PanelTemplates_GetSelectedTab(frame)
    local account,character=GetNumMacros()
    local count=tab==1 and account or tab==2 and character
    if count~=0 then return end
    frame:HideDetails()
    MacroFrameEnterMacroText:Hide()
    MacroDeleteButton:Disable()
    MacroEditButton:Disable()
end
local function install()
    if installed or not MacroFrame or type(MacroFrame.UpdateButtons)~='function' then return end
    hooksecurefunc(MacroFrame,'UpdateButtons',emptyDetails)
    installed=true
    Client442CompatibilityStatus.macro_empty_details_guard=true
    emptyDetails(MacroFrame)
end
local events=CreateFrame('Frame')
events:RegisterEvent('ADDON_LOADED')
events:RegisterEvent('PLAYER_LOGIN')
events:SetScript('OnEvent',install)
install()
