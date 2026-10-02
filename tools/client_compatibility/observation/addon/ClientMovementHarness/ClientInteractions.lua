-- Read-only public UI observations. This file never presses or invokes game controls.
local capacity,columns,cell=6144,128,3
local frame=CreateFrame('Frame','ClientInteractionHarnessPanel',UIParent)
frame:SetScale(1/UIParent:GetEffectiveScale());frame:SetSize(columns*cell,51)
frame:SetPoint('TOPLEFT',UIParent,'TOPLEFT',300,-16);frame:SetFrameStrata('TOOLTIP');frame:EnableMouse(false)
frame:SetFrameLevel(10000)
local pixels,previous={},{}
for i=1,math.ceil((capacity+12)/3) do
    local texture=frame:CreateTexture(nil,'OVERLAY');texture:SetSize(cell,cell)
    texture:SetPoint('TOPLEFT',frame,'TOPLEFT',((i-1)%columns)*cell,-math.floor((i-1)/columns)*cell)
    pixels[i]=texture
end
local panels={'CharacterFrame','PaperDollFrame','ReputationFrame','TokenFrame','SkillFrame','SpellBookFrame',
    'TradeSkillFrame','CraftFrame','ArchaeologyFrame','QuestLogFrame','WorldMapFrame','PlayerTalentFrame',
    'AchievementFrame','FriendsFrame','RaidFrame','GuildFrame','GuildInfoFrame','GuildMemberDetailFrame','GuildControlPopupFrame',
    'GuildFinderFrame','LookingForGuildFrame','CommunitiesFrame','PVEFrame','PVPUIFrame','PVPFrame',
    'EncounterJournal','CollectionsJournal','PetJournalParent','GameMenuFrame','SettingsPanel',
    'InterfaceOptionsFrame','VideoOptionsFrame','AudioOptionsFrame','KeyBindingFrame','MacroFrame','MacroPopupFrame',
    'ChatConfigFrame','HelpFrame','CalendarFrame','BankFrame','MerchantFrame','GossipFrame','QuestFrame',
    'MailFrame','AuctionFrame','AuctionHouseFrame','TradeFrame','InspectFrame','LootFrame','DressUpFrame','ItemTextFrame','ClassTrainerFrame',
    'PetStableFrame','GuildBankFrame','StaticPopup1','StaticPopup2','StaticPopup3','DropDownList1','DropDownList2','RolePollPopup','ReadyCheckFrame','StackSplitFrame'}
local sequence,elapsed,mode,page=0,0,'state',1
local autoPage,autoPages,groupPage=0,0,1
local errors={}
local chatProbes={}
local luaErrors={}
local blockedActions={}
local following={active=false}
local inspectionReady,tradeEvents,lastLoot={},{},nil
local observerSkips,skipKeys={},{}
local priorErrorHandler=geterrorhandler()
seterrorhandler(function(message)
    luaErrors[#luaErrors+1]=tostring(message):sub(1,300)
    if #luaErrors>3 then table.remove(luaErrors,1) end
    if priorErrorHandler then return priorErrorHandler(message) end
end)
local function call(fn,...)
    if type(fn)~='function' then return nil end
    local ok,a,b,c,d,e,f,g,h,i,j,k,l,m,n,o,p,q,r=pcall(fn,...)
    if ok then return a,b,c,d,e,f,g,h,i,j,k,l,m,n,o,p,q,r end
end
local function quoted(s)
    s=tostring(s or '')
    return '"'..s:gsub('[%z\1-\31\\"]',function(c)
        if c=='"' or c=='\\' then return '\\'..c end
        return string.format('\\u%04x',c:byte())
    end)..'"'
end
local function json(value)
    local t=type(value)
    if t=='nil' then return 'null' elseif t=='boolean' or t=='number' then return tostring(value)
    elseif t=='string' then return quoted(value) end
    local out={}
    if #value>0 then
        for _,v in ipairs(value) do out[#out+1]=json(v) end
        return '['..table.concat(out,',')..']'
    end
    local keys={};for k in pairs(value) do keys[#keys+1]=k end;table.sort(keys)
    for _,k in ipairs(keys) do out[#out+1]=quoted(k)..':'..json(value[k]) end
    return '{'..table.concat(out,',')..'}'
end
local function trim(s,n)return tostring(s or ''):sub(1,n or 60) end
local function caption(f)
    if f.GetText then local s=call(f.GetText,f);if s and s~='' then return trim(s) end end
    for _,field in ipairs({'Label','Text'}) do local r=f[field]
        if r and r.GetText then local s=call(r.GetText,r);if s and s~='' then return trim(s) end end
    end
    for _,r in ipairs({f:GetRegions()}) do
        if r.GetText then local s=call(r.GetText,r);if s and s~='' then return trim(s) end end
    end
    return ''
end
local function bindings(first,count)
    local rows={}
    for i=first,math.min(GetNumBindings(),first+count-1) do
        local name,category=GetBinding(i);local one,two=GetBindingKey(name)
        rows[#rows+1]={i=i,name=name,category=category,keys={one,two},caption=_G['BINDING_NAME_'..name]}
    end
    return rows
end
local function groupUnits(page)
    local rows={}
    for i=(page-1)*6+1,math.min(GetNumGroupMembers(),page*6) do
        local unit=IsInRaid() and 'raid'..i or (i==1 and 'player' or 'party'..(i-1))
        local _,class=call(UnitClass,unit)
        rows[#rows+1]={unit=unit,guid=call(UnitGUID,unit),name=call(UnitName,unit),exists=not not call(UnitExists,unit),
            connected=not not call(UnitIsConnected,unit),visible=not not call(UnitIsVisible,unit),class=class,
            assistant=not not call(UnitIsGroupAssistant,unit),leader=not not call(UnitIsGroupLeader,unit),
            role=call(UnitGroupRolesAssigned,unit),
            level=call(UnitLevel,unit),health=call(UnitHealth,unit),max_health=call(UnitHealthMax,unit),
            power=call(UnitPower,unit),max_power=call(UnitPowerMax,unit),dead=not not call(UnitIsDeadOrGhost,unit)}
    end
    return rows
end
local function groupFrames(units)
    local rows,visited,wanted={},{},{}
    for _,row in ipairs(units) do wanted[row.unit]=true end
    local function scan(f,depth)
        if not f or visited[f] or depth>5 or not f:IsVisible() then return end;visited[f]=true
        local unit=f.unit or f.displayedUnit or call(f.GetAttribute,f,'unit')
        if type(unit)=='string' and wanted[unit] and #rows<6 then
            local bar=f.healthBar or f.HealthBar or _G[(f:GetName() or '')..'HealthBar']
            if bar then
                local low,high=call(bar.GetMinMaxValues,bar)
                rows[#rows+1]={name=f:GetName() or '',unit=unit,visible=true,
                    health_bar=bar:IsVisible(),low=low,high=high,value=call(bar.GetValue,bar)}
            end
        end
        if f.GetChildren then for _,child in ipairs({f:GetChildren()}) do scan(child,depth+1) end end
    end
    for _,name in ipairs({'PartyFrame','CompactPartyFrame','CompactRaidFrameContainer','PartyMemberFrame1',
        'PartyMemberFrame2','PartyMemberFrame3','PartyMemberFrame4'}) do scan(_G[name],0) end
    return rows
end
local function snapshot(viewMode,viewPage)
    local mode,page=viewMode or mode,viewPage or page
    local data={mode=mode,build=tonumber((select(2,GetBuildInfo()))),interface=select(4,GetBuildInfo()),player=UnitName('player'),guid=UnitGUID('player'),
        level=UnitLevel('player'),binding_count=GetNumBindings(),errors=errors,lua_errors=luaErrors,
        blocked_actions=blockedActions,observer_version=13,observer_skips=observerSkips}
    if mode=='bindings' then data.page=page;data.rows=bindings((page-1)*12+1,12);return data end
    local profile=call(GetActiveRaidProfile)
    data.raid_profile={name=profile,count=call(GetNumRaidProfiles),locked=profile and call(GetRaidProfileOption,profile,'locked'),
        shown=profile and call(GetRaidProfileOption,profile,'shown'),expanded=CompactRaidFrameManager and not CompactRaidFrameManager.collapsed,
        bars_visible=CompactRaidFrameContainer and CompactRaidFrameContainer:IsVisible() or false}
    if mode=='group' then data.page=page;data.group_count=GetNumGroupMembers();data.everyone_assistant=call(IsEveryoneAssistant)
        data.units=groupUnits(page);data.frames=groupFrames(data.units);return data end
    data.panels={};data.controls={};data.bags={}
    local visited={};local width=GetScreenWidth()*UIParent:GetEffectiveScale()
    local height=GetScreenHeight()*UIParent:GetEffectiveScale()
    local function scan(f,depth)
        if not f or visited[f] or depth>12 then return end;visited[f]=true
        local ok,visible=pcall(f.IsVisible,f)
        if not ok then
            local name=call(f.GetName,f) or tostring(f)
            local key=name..':'..tostring(visible)
            if not skipKeys[key] and #observerSkips<6 then
                skipKeys[key]=true;observerSkips[#observerSkips+1]={name=trim(name,72),method='IsVisible',error=trim(visible,160)}
            end
            return
        end
        if not visible then return end
        local kind=f:GetObjectType()
        if kind=='Frame' and f.GetElementDescription and f:IsMouseEnabled() then kind='MenuItem' end
        if kind=='Frame' and f:IsMouseEnabled() and (f:GetName()=='GuildMemberNoteBackground' or
            f:GetName()=='GuildMemberOfficerNoteBackground') then kind='ClickFrame' end
        if (kind=='Button' or kind=='CheckButton' or kind=='EditBox' or kind=='Slider' or kind=='MenuItem' or kind=='ClickFrame') and #data.controls<512 then
            local x,y=f:GetCenter()
            if x and y then
                local scale=f:GetEffectiveScale();local name=f:GetName() or ''
                data.controls[#data.controls+1]={name=trim(name,72),text=caption(f),kind=kind,
                    context=f:GetParent() and caption(f:GetParent()) or '',
                    x=math.floor(x*scale/width*65535),y=math.floor((1-y*scale/height)*65535),
                    enabled=not f.IsEnabled or f:IsEnabled(),checked=call(f.GetChecked,f)}
                local parent=f:GetParent()
                local bag=call(f.GetBagID,f)
                if bag==nil and name:match('^ContainerFrame%d+Item%d+$') then bag=call(parent.GetID,parent) end
                if bag~=nil and f.GetID then
                    data.controls[#data.controls].bag_id=bag
                    data.controls[#data.controls].bag_slot=call(f.GetID,f)
                end
                local index=parent and parent.initializer and parent.initializer.data and parent.initializer.data.bindingIndex
                if index and (f==parent.Button1 or f==parent.Button2) then
                    data.controls[#data.controls].binding_action=call(GetBinding,index)
                    data.controls[#data.controls].binding_slot=f==parent.Button1 and 1 or 2
                end
            end
        end
        if f.GetChildren then for _,child in ipairs({f:GetChildren()}) do scan(child,depth+1) end end
    end
    for _,name in ipairs(panels) do
        local f=_G[name]
        if f and f:IsVisible() then data.panels[#data.panels+1]=name;scan(f,0) end
    end
    local manager=Menu and call(Menu.GetManager)
    local menu=manager and call(manager.GetOpenMenu,manager)
    if menu and menu.IsVisible and menu:IsVisible() then data.panels[#data.panels+1]='ContextMenu';scan(menu,0) end
    for i=1,13 do local f=_G['ContainerFrame'..i];if f and f:IsVisible() then
        data.bags[#data.bags+1]=f:GetID();scan(f,0)
    end end
    if ContainerFrameCombinedBags and ContainerFrameCombinedBags:IsVisible() then data.bags[#data.bags+1]=-1 end
    data.bag_slots={};for i=0,4 do data.bag_slots[i+1]=call(C_Container and C_Container.GetContainerNumSlots,i) or call(GetContainerNumSlots,i) or 0 end
    data.bag_items={}
    for bag=0,4 do for slot=1,data.bag_slots[bag+1] do
        local info=call(C_Container and C_Container.GetContainerItemInfo,bag,slot)
        if info and #data.bag_items<20 then
            data.bag_items[#data.bag_items+1]={bag=bag,slot=slot,id=info.itemID,count=info.stackCount,locked=info.isLocked}
        end
    end end
    data.reputations=call(GetNumFactions) or call(C_Reputation and C_Reputation.GetNumFactions)
    data.bank={visible=BankFrame and BankFrame:IsVisible() or false,items={}}
    if data.bank.visible then
        data.bank.slots=call(C_Container and C_Container.GetContainerNumSlots,-1) or 0
        for slot=1,math.min(data.bank.slots,28) do
            local info=call(C_Container and C_Container.GetContainerItemInfo,-1,slot)
            if info then data.bank.items[#data.bank.items+1]={bag=-1,slot=slot,id=info.itemID,count=info.stackCount,locked=info.isLocked} end
        end
    end
    data.currency_types=call(GetCurrencyListSize) or call(C_CurrencyInfo and C_CurrencyInfo.GetCurrencyListSize)
    data.money=call(GetMoney)
    data.last_loot=lastLoot
    data.merchant={visible=MerchantFrame and MerchantFrame:IsVisible() or false,items={}}
    if data.merchant.visible then
        data.merchant.count=call(GetMerchantNumItems);data.merchant.tab=MerchantFrame.selectedTab
        data.merchant.buyback_count=call(GetNumBuybackItems)
        data.merchant.repairable=call(CanMerchantRepair)
        if data.merchant.repairable then
            data.merchant.repair_cost,data.merchant.repair_needed=call(GetRepairAllCost)
            data.durability={}
            for slot=1,19 do
                local current,maximum=call(GetInventoryItemDurability,slot)
                data.durability[slot]={current or 0,maximum or 0}
            end
        end
        if data.merchant.tab==2 then
            data.merchant.buyback={}
            for index=1,math.min(data.merchant.buyback_count or 0,12) do
                local _,_,price,quantity=call(GetBuybackItemInfo,index)
                local link=call(GetBuybackItemLink,index)
                data.merchant.buyback[#data.merchant.buyback+1]={index=index,
                    id=link and tonumber(link:match('item:(%d+)')),price=price,count=quantity}
            end
        else
            for index=1,math.min(data.merchant.count or 0,12) do
                local _,_,price,quantity,available,usable=call(GetMerchantItemInfo,index)
                local link=call(GetMerchantItemLink,index)
                data.merchant.items[#data.merchant.items+1]={index=index,
                    id=link and tonumber(link:match('item:(%d+)')),price=price,quantity=quantity,available=available,usable=usable}
            end
        end
    end
    if ClassTrainerFrame and ClassTrainerFrame:IsVisible() then
        data.trainer={count=call(GetNumTrainerServices),selected=call(GetTrainerSelectionIndex),
            profession=call(IsTradeskillTrainer)}
        if data.trainer.selected then
            local name,rank,state=call(GetTrainerServiceInfo,data.trainer.selected)
            data.trainer.service={name=name,rank=rank,state=state,
                cost=call(GetTrainerServiceCost,data.trainer.selected),level=call(GetTrainerServiceLevelReq,data.trainer.selected)}
        end
    end
    data.trainer_probe={spell=3127,available=type(IsSpellKnown)=='function',known=call(IsSpellKnown,3127)}
    data.spell_tabs=call(GetNumSpellTabs);data.macros={GetNumMacros()};data.binding_set=call(GetCurrentBindingSet)
    data.test_macro={call(GetMacroInfo,'TC442Test')}
    data.role_poll=RolePollPopup and RolePollPopup:IsVisible() or false
    data.ready_check=ReadyCheckFrame and ReadyCheckFrame:IsVisible() or false
    data.ready_status=call(GetReadyCheckStatus,'player')
    data.role=call(UnitGroupRolesAssigned,'player')
    data.role_poll_checked={}
    for _,role in ipairs({'Tank','Healer','DPS'}) do
        local button=_G['RolePollPopupRoleButton'..role]
        data.role_poll_checked[role]=button and button.checkButton and not not call(button.checkButton.GetChecked,button.checkButton) or false
    end
    data.world_markers={};for i=1,8 do data.world_markers[i]=not not call(IsRaidMarkerActive,i) end
    data.spell_targeting=not not call(SpellIsTargeting)
    data.marker_spell_names={}
    for _,id in ipairs({171553,171554,171555,171556,171557}) do
        local info=call(C_Spell and C_Spell.GetSpellInfo,id)
        data.marker_spell_names[tostring(id)]=info and info.name or call(GetSpellInfo,id)
    end
    data.equipment={};for i=1,19 do data.equipment[i]=GetInventoryItemID('player',i) or 0 end
    data.professions={};if GetProfessions then
        for _,id in pairs({GetProfessions()}) do local name,_,rank,max=GetProfessionInfo(id)
            data.professions[#data.professions+1]={name=name,rank=rank,max=max}
        end
    end
    data.group={raid=IsInRaid(),members=GetNumGroupMembers(),leader=UnitIsGroupLeader('player'),everyone_assistant=call(IsEveryoneAssistant),names={}}
    for i=1,math.max(GetNumGroupMembers(),1) do
        local unit=IsInRaid() and 'raid'..i or (i==1 and 'player' or 'party'..(i-1))
        local name=UnitName(unit);if name then data.group.names[#data.group.names+1]=name end
    end
    data.friends={}
    if C_FriendList and C_FriendList.GetNumFriends then
        local friendCount=call(C_FriendList.GetNumFriends)
        data.friends_ready=type(friendCount)=='number'
        for i=1,math.min(tonumber(friendCount) or 0,10) do
            local f=C_FriendList.GetFriendInfoByIndex(i)
            if f then data.friends[#data.friends+1]={name=f.name,connected=f.connected,level=f.level,notes=trim(f.notes)} end
        end
    end
    for _,name in ipairs({'CharacterMicroButton','SpellbookMicroButton','TalentMicroButton','AchievementMicroButton',
        'QuestLogMicroButton','SocialsMicroButton','GuildMicroButton','EJMicroButton','CollectionsMicroButton',
        'PVPMicroButton','LFGMicroButton','MainMenuMicroButton','HelpMicroButton','GameTimeFrame','PlayerFrame','CompactRaidFrameManager'}) do
        local f=_G[name];if f then scan(f,0) end
    end
    data.control_count=#data.controls
    local controls={};local first=mode=='controls' and (page-1)*12+1 or 1
    for _,control in ipairs(data.controls) do if control.name=='GameTimeFrame' then data.calendar_button=control end end
    for i=first,math.min(#data.controls,first+(mode=='controls' and 11 or 5)) do controls[#controls+1]=data.controls[i] end
    data.controls=controls
    if mode=='controls' then
        return {mode=mode,page=page,build=data.build,guid=data.guid,player=data.player,
            panels=data.panels,bags=data.bags,controls=controls,control_count=data.control_count,page_size=12}
    end
    data.trade_skill={call(GetTradeSkillLine)};data.recipe_count=call(GetNumTradeSkills)
    data.recipe_selection=call(GetTradeSkillSelectionIndex)
    if data.recipe_selection and data.recipe_selection>0 then
        local id=data.recipe_selection
        data.selected_recipe={name=call(GetTradeSkillInfo,id),link=call(GetTradeSkillItemLink,id),
            reagents=call(GetTradeSkillNumReagents,id),cooldown=call(GetTradeSkillCooldown,id),
            recipe_link=call(GetTradeSkillRecipeLink,id)}
        data.recipe_reagents={}
        for i=1,math.min(data.selected_recipe.reagents or 0,8) do
            local name,_,need,have=call(GetTradeSkillReagentInfo,id,i)
            data.recipe_reagents[#data.recipe_reagents+1]={name=name,need=need,have=have,link=call(GetTradeSkillReagentItemLink,id,i)}
        end
    end
    data.crafting_probe={known=not not call(IsSpellKnown,2330),deepholm_known=not not call(IsSpellKnown,80725),counts={}}
    for _,id in ipairs({118,765,2447,3371,52986,58487}) do
        data.crafting_probe.counts[tostring(id)]=call(C_Item and C_Item.GetItemCount or GetItemCount,id)
    end
    data.chat_probes=chatProbes
    data.player_stats={health=call(UnitHealthMax,'player'),armor={call(UnitArmor,'player')},
        strength={call(UnitStat,'player',1)},damage={call(UnitDamage,'player')}}
    data.target={guid=call(UnitGUID,'target'),name=call(UnitName,'target'),
        exists=not not call(UnitExists,'target'),visible=not not call(UnitIsVisible,'target'),
        player=not not call(UnitIsPlayer,'target'),health=call(UnitHealth,'target'),
        max_health=call(UnitHealthMax,'target'),position={call(UnitPosition,'target')}}
    data.follow=following
    data.inspect={ready=inspectionReady,visible=InspectFrame and InspectFrame:IsVisible() or false}
    if data.inspect.visible then
        local unit=InspectFrame.unit or 'target'
        data.inspect.unit=unit;data.inspect.guid=call(UnitGUID,unit);data.inspect.name=call(UnitName,unit)
        data.inspect.items={}
        for _,slot in ipairs({1,16,17}) do
            local link=call(GetInventoryItemLink,unit,slot)
            if link then data.inspect.items[#data.inspect.items+1]={slot=slot,link=trim(link,240)} end
        end
    end
    data.trade={events=tradeEvents,visible=TradeFrame and TradeFrame:IsVisible() or false}
    if data.trade.visible then
        data.trade.partner=TradeFrameRecipientNameText and call(TradeFrameRecipientNameText.GetText,TradeFrameRecipientNameText)
        data.trade.money=call(GetPlayerTradeMoney);data.trade.target_money=call(GetTargetTradeMoney)
        data.trade.items={};data.trade.target_items={}
        for slot=1,7 do
            local name,_,count=call(GetTradePlayerItemInfo,slot)
            if name then data.trade.items[#data.trade.items+1]={slot=slot,name=trim(name),count=count} end
            name,_,count=call(GetTradeTargetItemInfo,slot)
            if name then data.trade.target_items[#data.trade.target_items+1]={slot=slot,name=trim(name),count=count} end
        end
    end
    data.world_position={call(UnitPosition,'player')}
    data.quests={}
    local questCount=call(C_QuestLog and C_QuestLog.GetNumQuestLogEntries or GetNumQuestLogEntries)
    data.quest_entry_count=questCount
    data.quest_log_keys={call(GetBindingKey,'TOGGLEQUESTLOG')}
    for i=1,math.min(tonumber(questCount) or 0,8) do
        local q=call(C_QuestLog and C_QuestLog.GetInfo,i)
        if type(q)~='table' then
            local title,level,group,header,collapsed,complete,frequency,id=call(GetQuestLogTitle,i)
            if title then q={title=title,level=level,isHeader=header,isComplete=complete,questID=id} end
        end
        if q and not q.isHeader then
            local row={index=i,id=q.questID,title=trim(q.title,80),level=q.level,complete=q.isComplete,objectives={}}
            local objectives=call(C_QuestLog and C_QuestLog.GetQuestObjectives,q.questID)
            for _,objective in ipairs(type(objectives)=='table' and objectives or {}) do
                row.objectives[#row.objectives+1]={text=trim(objective.text,120),type=objective.type,
                    fulfilled=objective.numFulfilled,required=objective.numRequired,finished=objective.finished}
                if #row.objectives>=4 then break end
            end
            data.quests[#data.quests+1]=row
        end
    end
    data.quest_giver={id=call(GetQuestID),title=trim(call(GetTitleText),80),
        description=trim(call(GetQuestText),180),objectives=trim(call(GetObjectiveText),120)}
    data.rest_info={call(GetRestState)};data.xp=call(UnitXP,'player');data.xp_max=call(UnitXPMax,'player')
    data.xp_exhaustion=call(GetXPExhaustion)
    data.guild_ui={classic=call(GetCVarBool,'useClassicGuildUI'),in_guild=call(IsInGuild),
        trial=call(IsTrialAccount),veteran_trial=call(IsVeteranTrialAccount),
        clubs_enabled=call(C_Club and C_Club.IsEnabled),bn_connected=call(BNConnected)}
    local guildName,guildRank,guildRankIndex=call(GetGuildInfo,'player')
    data.guild_ui.name=guildName;data.guild_ui.rank=guildRank;data.guild_ui.rank_index=guildRankIndex
    data.guild_ui.motd=trim(call(GetGuildRosterMOTD));data.guild_ui.info=trim(call(GetGuildInfoText))
    data.guild_ui.permissions={invite=call(CanGuildInvite),motd=call(CanEditMOTD),
        public_note=call(CanEditPublicNote),officer_note=call(CanEditOfficerNote),promote=call(CanGuildPromote)}
    data.guild_ui.compatibility=Client442CompatibilityStatus
    local guildCount=call(GetNumGuildMembers)
    data.guild_ui.member_count=guildCount;data.guild_ui.members={}
    for i=1,math.min(tonumber(guildCount) or 0,4) do
        local name,rank,rankIndex,level,class,zone,note,officer,online=call(GetGuildRosterInfo,i)
        if name then data.guild_ui.members[#data.guild_ui.members+1]={name=name,rank=rank,index=rankIndex,
            level=level,class=class,zone=zone,note=trim(note),officer=trim(officer),online=online} end
    end
    data.binding_probe=call(GetBindingAction,'CTRL-SHIFT-F12')
    data.fps_keys={call(GetBindingKey,'TOGGLEFPS')}
    data.keybind_listening=KeybindListener and KeybindListener.pending and
        {action=KeybindListener.pending.action,slot=KeybindListener.pending.slotIndex} or false
    data.chat_edit_open=ChatFrame1EditBox and ChatFrame1EditBox:IsVisible() or false
    data.chat_edit_text=data.chat_edit_open and trim(ChatFrame1EditBox:GetText(),255) or ''
    data.item_cursor=not not call(CursorHasItem)
    data.framerate_visible=FramerateLabel and FramerateLabel:IsVisible() or false
    data.input_aliases={}
    for _,name in ipairs({'LEAVEPARTY','PARTYLEAVE','INVITE','UNINVITE','FRIENDS','REMOVEFRIEND','RAID','READY_CHECK'}) do
        local aliases={}
        for i=1,5 do local alias=_G['SLASH_'..name..i];if alias then aliases[#aliases+1]=alias end end
        data.input_aliases[name]=aliases
    end
    data.group_aliases={}
    for name,value in pairs(_G) do
        if type(name)=='string' and name:match('^SLASH_.*%d$') and type(value)=='string' and
            (name:find('PARTY') or name:find('GROUP') or name:find('LEAVE')) then data.group_aliases[name]=value end
    end
    local actionButton=_G.ActionButton12
    local slot=actionButton and actionButton.action or 12
    local kind,id=call(GetActionInfo,slot)
    data.action_probe={slot=slot,kind=kind,id=id,macro=kind=='macro' and call(GetMacroInfo,id) or nil}
    if actionButton then local x,y=actionButton:GetCenter()
        data.action_probe.point={math.floor(x*actionButton:GetEffectiveScale()/width*65535),
            math.floor((1-y*actionButton:GetEffectiveScale()/height)*65535)}
    end
    data.buffs={}
    for i=1,20 do local aura=call(C_UnitAuras and C_UnitAuras.GetBuffDataByIndex,'player',i)
        if not aura then break end
        data.buffs[#data.buffs+1]=aura.spellId
    end
    return data
end
local function append(bytes,value,n)
    for power=n-1,0,-1 do bytes[#bytes+1]=math.floor(value/256^power)%256 end
end
local function update()
    sequence=(sequence+1)%4294967296
    local viewMode,viewPage=mode,page
    if mode=='state' and autoPage==-1 then viewMode,viewPage='group',groupPage
    elseif mode=='state' and autoPage>0 then viewMode,viewPage='controls',autoPage end
    local ok,data=pcall(snapshot,viewMode,viewPage)
    if mode=='state' and ok then
        if viewMode=='state' then autoPages=math.ceil((data.control_count or 0)/12);autoPage=-1;groupPage=1
        elseif viewMode=='group' then
            if groupPage<math.ceil((data.group_count or 0)/6) then groupPage=groupPage+1
            else autoPage=autoPages>0 and 1 or 0 end
        else autoPage=autoPage<autoPages and autoPage+1 or 0 end
    end
    if not ok then data={observer_error=trim(data,250),mode=mode} end
    local payload=json(data)
    if #payload>capacity then payload=json({observer_error='UI observation exceeds packet capacity',mode=mode,bytes=#payload}) end
    local bytes={84,67,85,50};append(bytes,#payload,2);append(bytes,sequence,4)
    for i=1,#payload do bytes[#bytes+1]=payload:byte(i) end
    local first,second=0,0;for _,byte in ipairs(bytes) do first=(first+byte)%255;second=(second+first)%255 end
    append(bytes,second*256+first,2)
    for i=1,math.ceil(#bytes/3) do
        local r,g,b=bytes[(i-1)*3+1] or 0,bytes[(i-1)*3+2] or 0,bytes[(i-1)*3+3] or 0
        local code=r*65536+g*256+b
        if previous[i]~=code then pixels[i]:SetColorTexture(r/255,g/255,b/255,1);previous[i]=code end
    end
end
SLASH_CLIENTINTERACTIONHARNESS1='/tcui'
SLASH_CLIENTOBSERVERPANELS1='/tcoverlays'
SlashCmdList.CLIENTOBSERVERPANELS=function(text)
    local show=text~='off'
    for _,name in ipairs({'ClientMovementHarnessPanel','ClientTaxiHarnessPanel','ClientGossipHarnessPanel','ClientInteractionHarnessPanel'}) do
        local panel=_G[name];if panel then panel:SetShown(show) end
    end
end
SlashCmdList.CLIENTINTERACTIONHARNESS=function(text)
    local command,arg=text:match('^(%S+)%s*(.*)$')
    if command=='bindings' or command=='controls' then mode=command;page=math.max(1,tonumber(arg) or 1)
    elseif command=='hide' then frame:Hide();return
    else mode='state';autoPage=0 end
    frame:Show();update()
end
frame:RegisterEvent('UI_ERROR_MESSAGE')
frame:RegisterEvent('ADDON_ACTION_BLOCKED');frame:RegisterEvent('ADDON_ACTION_FORBIDDEN')
frame:RegisterEvent('AUTOFOLLOW_BEGIN');frame:RegisterEvent('AUTOFOLLOW_END')
frame:RegisterEvent('INSPECT_READY')
frame:RegisterEvent('CHAT_MSG_LOOT')
for _,event in ipairs({'TRADE_SHOW','TRADE_CLOSED','TRADE_REQUEST_CANCEL','TRADE_ACCEPT_UPDATE'}) do frame:RegisterEvent(event) end
for _,event in ipairs({'CHAT_MSG_SYSTEM','CHAT_MSG_SAY','CHAT_MSG_YELL','CHAT_MSG_PARTY','CHAT_MSG_PARTY_LEADER',
    'CHAT_MSG_RAID','CHAT_MSG_RAID_LEADER','CHAT_MSG_RAID_WARNING','CHAT_MSG_WHISPER','CHAT_MSG_WHISPER_INFORM',
    'CHAT_MSG_EMOTE','CHAT_MSG_CHANNEL','CHAT_MSG_GUILD','CHAT_MSG_OFFICER'}) do frame:RegisterEvent(event) end
frame:SetScript('OnEvent',function(_,event,code,text)
    if event=='AUTOFOLLOW_BEGIN' then following={active=true,name=trim(code,64)}
    elseif event=='AUTOFOLLOW_END' then following={active=false}
    elseif event=='INSPECT_READY' then inspectionReady={guid=trim(code,64),time=GetTime()}
    elseif event=='CHAT_MSG_LOOT' and type(code)=='string' then
        lastLoot={id=tonumber(code:match('item:(%d+)')),count=tonumber(code:match('x(%d+)')) or 1,time=GetTime()}
    elseif event:match('^TRADE_') then
        tradeEvents[#tradeEvents+1]={event=event,own=code,peer=text,time=GetTime()}
        if #tradeEvents>3 then table.remove(tradeEvents,1) end
    elseif event=='UI_ERROR_MESSAGE' then
        errors[#errors+1]={code=code,text=trim(text,120)};if #errors>3 then table.remove(errors,1) end
    elseif event=='ADDON_ACTION_BLOCKED' or event=='ADDON_ACTION_FORBIDDEN' then
        blockedActions[#blockedActions+1]={event=event,addon=trim(code,64),action=trim(text,80)}
        if #blockedActions>3 then table.remove(blockedActions,1) end
    elseif type(code)=='string' and code:match('^TC442UI:[%w_-]+$') then
        chatProbes[#chatProbes+1]={event=event,text=code,sender=trim(text,64),time=GetTime()}
        if #chatProbes>4 then table.remove(chatProbes,1) end
    end
end)
frame:SetScript('OnUpdate',function(_,delta)elapsed=elapsed+delta;if elapsed>=.5 then elapsed=0;update() end end)
update()
