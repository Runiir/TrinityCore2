-- 60895 Cata XML calls OnClick directly and omits OnModifiedClick dispatch.
-- Route only a user's chat-link click to the existing stock link handler.
if tonumber((select(2,GetBuildInfo())))~=60895 then return end
local installed=false
local function install()
    if installed or not SpellButton1 then return end
    for index=1,12 do
        local frame=_G['SpellButton'..index]
        if not frame or type(frame.OnModifiedClick)~='function' then return end
    end
    for index=1,12 do
        local frame=_G['SpellButton'..index]
        local original=frame:GetScript('OnClick')
        frame:SetScript('OnClick',function(self,button,...)
            if IsModifiedClick('CHATLINK') then
                return self:OnModifiedClick(button)
            end
            if original then return original(self,button,...) end
        end)
    end
    installed=true
    Client442CompatibilityStatus.spell_chat_link_dispatch=true
end
local events=CreateFrame('Frame')
events:RegisterEvent('ADDON_LOADED');events:RegisterEvent('PLAYER_LOGIN')
events:SetScript('OnEvent',install)
install()
