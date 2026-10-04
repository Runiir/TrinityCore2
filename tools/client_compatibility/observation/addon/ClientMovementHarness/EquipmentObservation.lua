-- Public stock equipment-set state. No setters or gameplay API calls.
local function read(fn,...)
    if type(fn)~='function' then return nil end
    local ok,a,b,c,d,e,f,g,h,i=pcall(fn,...)
    if ok then return a,b,c,d,e,f,g,h,i end
end
function Client442ObserveEquipment()
    local api=C_EquipmentSet or {}
    local ids=read(api.GetEquipmentSetIDs) or {}
    local rows={}
    for _,id in ipairs(ids) do
        if #rows>=20 then break end
        local name,icon,setID,equipped,total,worn,stored,lost,ignored=read(api.GetEquipmentSetInfo,id)
        rows[#rows+1]={id=id,name=name,icon=icon,set_id=setID,equipped=equipped,
            total=total,worn=worn,stored=stored,lost=lost,ignored=ignored,
            spec=read(api.GetEquipmentSetAssignedSpec,id)}
    end
    local pane=PaperDollFrame and PaperDollFrame.EquipmentManagerPane
    local spec=C_SpecializationInfo or {}
    local compat=Client442CompatibilityStatus or {}
    local titlePane=PaperDollFrame and PaperDollFrame.TitleManagerPane
    local titleCount=read(GetNumTitles) or 0
    local titles,known={},0
    if type(titleCount)=='number' and titleCount>=0 and titleCount<=1024 then
        for id=1,titleCount do
            if read(IsTitleKnown,id) then
                known=known+1
                if #titles<16 then local name,valid=read(GetTitleName,id)
                    titles[#titles+1]={id=id,name=name,valid=valid} end
            end
        end
    end
    local sheet,categories={},{}
    local spellCrit={}
    local ratings={}
    for school=1,7 do spellCrit[school]=read(GetSpellCritChance,school) end
    for index=1,26 do ratings[index]=read(GetCombatRating,index) end
    local scene=CharacterModelScene
    local camera=scene and read(scene.GetActiveCamera,scene)
    for category=1,8 do
        local parent=_G['CharacterStatsPaneCategory'..category]
        if parent and read(parent.IsVisible,parent) then
            categories[#categories+1]={name=parent:GetName(),category=parent.Category,collapsed=not not parent.collapsed}
            for index=1,12 do
                local name=parent:GetName()..'Stat'..index
                local stat,label,text=_G[name],_G[name..'Label'],_G[name..'StatText']
                if stat and read(stat.IsVisible,stat) and #sheet<24 then
                    sheet[#sheet+1]={name=name,category=parent.Category,
                        label=label and read(label.GetText,label),text=text and read(text.GetText,text)}
                end
            end
        end
    end
    return {count=read(api.GetNumEquipmentSets),sets=rows,
        model={visible=scene and not not read(scene.IsVisible,scene) or false,
            yaw=camera and read(camera.GetYaw,camera)},
        stats={damage={read(UnitDamage,'player')},attack_speed={read(UnitAttackSpeed,'player')},
            ranged_damage={read(UnitRangedDamage,'player')},crit=read(GetCritChance),
            ranged_crit=read(GetRangedCritChance),spell_crit=spellCrit,
            melee_haste=read(GetMeleeHaste),ranged_haste=read(GetRangedHaste),spell_haste=read(UnitSpellHaste,'player'),
            ratings=ratings,expertise={read(GetExpertise)},expertise_percent={read(GetExpertisePercent)},
            mastery=read(GetMastery),dodge=read(GetDodgeChance),parry=read(GetParryChance),
            block=read(GetBlockChance),shield_block=read(GetShieldBlock),
            attack_power={read(UnitAttackPower,'player')},item_level={read(GetAverageItemLevel)},sheet=sheet,
            categories=categories,category_settings={order=read(GetCVar,'statCategoryOrder'),
                collapsed=read(GetCVar,'statCategoriesCollapsed'),order_2=read(GetCVar,'statCategoryOrder_2'),
                collapsed_2=read(GetCVar,'statCategoriesCollapsed_2')}},
        manager_visible=pane and not not read(pane.IsVisible,pane) or false,
        selected=pane and pane.selectedSetID,
        popup_visible=GearManagerPopupFrame and not not read(GearManagerPopupFrame.IsVisible,GearManagerPopupFrame) or false,
        helm=read(ShowingHelm),cloak=read(ShowingCloak),
        display_apis={helm=type(ShowingHelm),cloak=type(ShowingCloak),
            show_helm=type(ShowHelm),show_cloak=type(ShowCloak)},
        titles={available=titleCount,known=known,rows=titles,current=read(GetCurrentTitle),
            pane_visible=titlePane and not not read(titlePane.IsVisible,titlePane) or false},
        compatibility={menu_version=compat.equipment_menu_version,menu_repaired=compat.equipment_menu_repaired,
            assignment_available=compat.equipment_assignment_available},
        specialization_apis={legacy_count=type(GetNumSpecializations),legacy_info=type(GetSpecializationInfo),
            legacy_by_id=type(GetSpecializationInfoByID),namespace_count=type(spec.GetNumSpecializations),
            namespace_info=type(spec.GetSpecializationInfo),namespace_by_id=type(spec.GetSpecializationInfoByID),
            talent_groups=read(GetNumTalentGroups),active_group=read(GetActiveTalentGroup)}}
end
