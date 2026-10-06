-- Passive stock event/lifecycle hooks. Never replace scripts or invoke controls.
local entries,hooked={},setmetatable({},{__mode='k'})
local events=CreateFrame('Frame')
local function visible(frame)
    return frame and frame:IsVisible() or false
end
local function retain(kind,frame,stack)
    local parent=SpellFlyout and SpellFlyout:GetParent()
    entries[#entries+1]={kind=kind,time=GetTime(),frame=frame and frame:GetName(),
        parent=parent and parent:GetName(),visible=visible(SpellFlyout),stack=stack}
    if #entries>6 then table.remove(entries,1) end
end
for _,event in ipairs({'SPELLS_CHANGED','UPDATE_SHAPESHIFT_FORM','PET_BAR_UPDATE',
    'CURSOR_CHANGED','ACTIONBAR_PAGE_CHANGED','PET_STABLE_UPDATE','PET_STABLE_SHOW',
    'SPELL_FLYOUT_UPDATE','LEARNED_SPELL_IN_TAB','SKILL_LINES_CHANGED'}) do
    events:RegisterEvent(event)
end
events:SetScript('OnEvent',function(_,event)
    if visible(SpellBookFrame) or visible(SpellFlyout) then retain(event) end
end)
function Client442ObserveSpellBookLifecycle()
    local flyout=SpellFlyout
    if flyout and not hooked[flyout] then
        hooked[flyout]=true
        flyout:HookScript('OnShow',function(self) retain('flyout_show',self) end)
        flyout:HookScript('OnHide',function(self)
            local stack=type(debugstack)=='function' and debugstack(2,6,0):sub(1,700) or nil
            retain('flyout_hide',self,stack)
        end)
    end
    return entries
end
