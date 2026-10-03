-- Repair the shipped 60895 Cata name/icon menu. Gameplay APIs stay unchanged.
-- The stock builder calls absent retail specialization APIs, then passes the
-- edit button instead of its owning gear row to GearSetButton_OpenPopup.
if tonumber((select(2,GetBuildInfo())))~=60895 then return end
local repaired=false
local function repair()
    if repaired or type(GearSetEditButton_OnMouseDown)~='function' then return end
    if type(GetNumSpecializations)=='function' and type(GetSpecializationInfo)=='function' then return end
    if not MenuUtil or not GearSetButton_OpenPopup then return end
    GearSetEditButton_OnMouseDown=function(self,button)
        self.texture:SetPoint('TOPLEFT',1,-1)
        local row=self:GetParent()
        MenuUtil.CreateContextMenu(PaperDollFrame.EquipmentManagerPane,function(dropdown,root)
            root:SetTag('MENU_PAPERDOLL_FRAME')
            root:CreateButton(EQUIPMENT_SET_EDIT,function() GearSetButton_OpenPopup(row) end)
        end)
    end
    repaired=true
    Client442CompatibilityStatus=Client442CompatibilityStatus or {}
    Client442CompatibilityStatus.equipment_menu_version=1
    Client442CompatibilityStatus.equipment_menu_repaired=true
    Client442CompatibilityStatus.equipment_assignment_available=false
end
local events=CreateFrame('Frame')
events:RegisterEvent('ADDON_LOADED');events:RegisterEvent('PLAYER_LOGIN')
events:SetScript('OnEvent',repair)
repair()
