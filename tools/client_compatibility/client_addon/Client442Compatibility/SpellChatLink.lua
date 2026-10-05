-- 60895 Cata XML calls OnClick directly and omits OnModifiedClick dispatch.
-- Route only a user's chat-link click to the existing stock link handler.
if tonumber((select(2,GetBuildInfo())))~=60895 then return end
local installed=false
local function install()
    if installed or not SpellButton1 or type(SecureHandlerWrapScript)~='function' then return end
    for index=1,12 do
        local frame=_G['SpellButton'..index]
        if not frame or type(frame.OnModifiedClick)~='function' then return end
    end
    local header=CreateFrame('Frame',nil,nil,'SecureHandlerBaseTemplate')
    for index=1,12 do
        local frame=_G['SpellButton'..index]
        frame.Client442ChatLink=function(self,button) self:OnModifiedClick(button) end
        -- The built-in secure wrapper retains the original stock script.
        -- Only link insertion crosses into our insecure UI callback.
        SecureHandlerWrapScript(frame,'OnClick',header,[=[
            if IsModifiedClick('CHATLINK') then
                self:CallMethod('Client442ChatLink',button)
                return false
            end
        ]=])
    end
    installed=true
    Client442CompatibilityStatus.spell_chat_link_dispatch=true
end
local events=CreateFrame('Frame')
events:RegisterEvent('ADDON_LOADED');events:RegisterEvent('PLAYER_LOGIN')
events:SetScript('OnEvent',install)
install()
