-- Read-only public UI observations. This file never presses or invokes game controls.
local capacity,columns,cell=4096,128,3
local frame=CreateFrame('Frame','ClientInteractionHarnessPanel',UIParent)
frame:SetScale(1/UIParent:GetEffectiveScale());frame:SetSize(columns*cell,36)
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
    'AchievementFrame','FriendsFrame','RaidFrame','GuildFrame','GuildFinderFrame','LookingForGuildFrame','PVEFrame','PVPUIFrame','PVPFrame',
    'EncounterJournal','CollectionsJournal','PetJournalParent','GameMenuFrame','SettingsPanel',
    'InterfaceOptionsFrame','VideoOptionsFrame','AudioOptionsFrame','KeyBindingFrame','MacroFrame','MacroPopupFrame',
    'ChatConfigFrame','HelpFrame','CalendarFrame','BankFrame','MerchantFrame','GossipFrame','QuestFrame',
    'MailFrame','AuctionFrame','AuctionHouseFrame','TradeFrame','LootFrame','DressUpFrame','ItemTextFrame',
    'PetStableFrame','GuildBankFrame','StaticPopup1','StaticPopup2','StaticPopup3','DropDownList1','DropDownList2'}
local sequence,elapsed,mode,page=0,0,'state',1
local autoPage,autoPages=0,0
local errors={}
local function call(fn,...)
    if type(fn)~='function' then return nil end
    local ok,a,b,c,d,e,f,g=pcall(fn,...)
    if ok then return a,b,c,d,e,f,g end
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
local function snapshot(viewMode,viewPage)
    local mode,page=viewMode or mode,viewPage or page
    local data={mode=mode,build=tonumber((select(2,GetBuildInfo()))),interface=select(4,GetBuildInfo()),player=UnitName('player'),guid=UnitGUID('player'),
        level=UnitLevel('player'),binding_count=GetNumBindings(),errors=errors}
    if mode=='bindings' then data.page=page;data.rows=bindings((page-1)*12+1,12);return data end
    data.panels={};data.controls={};data.bags={}
    local visited={};local width=GetScreenWidth()*UIParent:GetEffectiveScale()
    local height=GetScreenHeight()*UIParent:GetEffectiveScale()
    local function scan(f,depth)
        if visited[f] or depth>6 or not f:IsVisible() then return end;visited[f]=true
        local kind=f:GetObjectType()
        if (kind=='Button' or kind=='CheckButton' or kind=='EditBox' or kind=='Slider') and #data.controls<512 then
            local x,y=f:GetCenter()
            if x and y then
                local scale=f:GetEffectiveScale();local name=f:GetName() or ''
                data.controls[#data.controls+1]={name=trim(name,72),text=caption(f),kind=kind,
                    context=f:GetParent() and caption(f:GetParent()) or '',
                    x=math.floor(x*scale/width*65535),y=math.floor((1-y*scale/height)*65535),
                    enabled=not f.IsEnabled or f:IsEnabled(),checked=call(f.GetChecked,f)}
            end
        end
        if f.GetChildren then for _,child in ipairs({f:GetChildren()}) do scan(child,depth+1) end end
    end
    for _,name in ipairs(panels) do
        local f=_G[name]
        if f and f:IsVisible() then data.panels[#data.panels+1]=name;scan(f,0) end
    end
    for i=1,13 do local f=_G['ContainerFrame'..i];if f and f:IsVisible() then
        data.bags[#data.bags+1]=f:GetID();scan(f,0)
    end end
    if ContainerFrameCombinedBags and ContainerFrameCombinedBags:IsVisible() then data.bags[#data.bags+1]=-1 end
    data.bag_slots={};for i=0,4 do data.bag_slots[i+1]=call(C_Container and C_Container.GetContainerNumSlots,i) or call(GetContainerNumSlots,i) or 0 end
    data.reputations=call(GetNumFactions) or call(C_Reputation and C_Reputation.GetNumFactions)
    data.currency_types=call(GetCurrencyListSize) or call(C_CurrencyInfo and C_CurrencyInfo.GetCurrencyListSize)
    data.spell_tabs=call(GetNumSpellTabs);data.macros={GetNumMacros()};data.binding_set=call(GetCurrentBindingSet)
    data.test_macro={call(GetMacroInfo,'TC442Test')}
    data.equipment={};for i=1,19 do data.equipment[i]=GetInventoryItemID('player',i) or 0 end
    data.professions={};if GetProfessions then
        for _,id in pairs({GetProfessions()}) do local name,_,rank,max=GetProfessionInfo(id)
            data.professions[#data.professions+1]={name=name,rank=rank,max=max}
        end
    end
    data.group={raid=IsInRaid(),members=GetNumGroupMembers(),leader=UnitIsGroupLeader('player'),names={}}
    for i=1,math.max(GetNumGroupMembers(),1) do
        local unit=IsInRaid() and 'raid'..i or (i==1 and 'player' or 'party'..(i-1))
        local name=UnitName(unit);if name then data.group.names[#data.group.names+1]=name end
    end
    data.friends={}
    if C_FriendList and C_FriendList.GetNumFriends then
        for i=1,math.min(C_FriendList.GetNumFriends(),10) do
            local f=C_FriendList.GetFriendInfoByIndex(i)
            if f then data.friends[#data.friends+1]={name=f.name,connected=f.connected,level=f.level,notes=trim(f.notes)} end
        end
    end
    for _,name in ipairs({'CharacterMicroButton','SpellbookMicroButton','TalentMicroButton','AchievementMicroButton',
        'QuestLogMicroButton','SocialsMicroButton','GuildMicroButton','EJMicroButton','CollectionsMicroButton',
        'PVPMicroButton','LFGMicroButton','MainMenuMicroButton','HelpMicroButton','GameTimeFrame'}) do
        local f=_G[name];if f then scan(f,0) end
    end
    data.control_count=#data.controls
    local controls={};local first=mode=='controls' and (page-1)*18+1 or 1
    for i=first,math.min(#data.controls,first+17) do controls[#controls+1]=data.controls[i] end
    data.controls=controls
    if mode=='controls' then
        return {mode=mode,page=page,build=data.build,guid=data.guid,player=data.player,
            panels=data.panels,bags=data.bags,controls=controls,control_count=data.control_count}
    end
    data.trade_skill={call(GetTradeSkillLine)};data.recipe_count=call(GetNumTradeSkills)
    data.binding_probe=call(GetBindingAction,'CTRL-SHIFT-F12')
    data.framerate_visible=FramerateLabel and FramerateLabel:IsVisible() or false
    data.input_aliases={}
    for _,name in ipairs({'LEAVEPARTY','PARTYLEAVE','INVITE','UNINVITE','FRIENDS','REMOVEFRIEND','RAID','READY_CHECK'}) do
        local aliases={}
        for i=1,5 do local alias=_G['SLASH_'..name..i];if alias then aliases[#aliases+1]=alias end end
        data.input_aliases[name]=aliases
    end
    local actionButton=_G.ActionButton12
    local slot=actionButton and actionButton.action or 12
    local kind,id=call(GetActionInfo,slot)
    data.action_probe={slot=slot,kind=kind,id=id,macro=kind=='macro' and call(GetMacroInfo,id) or nil}
    return data
end
local function append(bytes,value,n)
    for power=n-1,0,-1 do bytes[#bytes+1]=math.floor(value/256^power)%256 end
end
local function update()
    sequence=(sequence+1)%4294967296
    local viewMode,viewPage=mode,page
    if mode=='state' and autoPage>0 then viewMode,viewPage='controls',autoPage end
    local ok,data=pcall(snapshot,viewMode,viewPage)
    if mode=='state' and ok then
        if viewMode=='state' then autoPages=math.ceil((data.control_count or 0)/18);autoPage=autoPages>0 and 1 or 0
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
SlashCmdList.CLIENTINTERACTIONHARNESS=function(text)
    local command,arg=text:match('^(%S+)%s*(.*)$')
    if command=='bindings' or command=='controls' then mode=command;page=math.max(1,tonumber(arg) or 1)
    elseif command=='hide' then frame:Hide();return
    else mode='state';autoPage=0 end
    frame:Show();update()
end
frame:RegisterEvent('UI_ERROR_MESSAGE');frame:SetScript('OnEvent',function(_,_,code,text)
    errors[#errors+1]={code=code,text=trim(text,120)};if #errors>3 then table.remove(errors,1) end
end)
frame:SetScript('OnUpdate',function(_,delta)elapsed=elapsed+delta;if elapsed>=.5 then elapsed=0;update() end end)
update()
