-- Observe stock spellbook state and public spell APIs. No gameplay setters.
local function read(fn,...)
    if type(fn)~='function' then return nil end
    local ok,a,b,c,d,e,f,g,h=pcall(fn,...)
    if ok then return a,b,c,d,e,f,g,h end
end
local function text(frame)
    local value=frame and read(frame.GetText,frame)
    return type(value)=='string' and value:sub(1,96) or nil
end
function Client442ObserveSpellBook()
    local book=SpellBookFrame
    local tabs,rows,pages={},{},{}
    for index=1,math.min(read(GetNumSpellTabs) or 0,8) do
        local name,texture,offset,count,guild,offspec,hidden,spec=read(GetSpellTabInfo,index)
        local tab=_G['SpellBookSkillLineTab'..index]
        tabs[#tabs+1]={index=index,name=name,offset=offset,count=count,guild=guild,
            offspec=offspec,hidden=hidden,spec=spec,checked=tab and read(tab.GetChecked,tab)}
        pages[tostring(index)]=SPELLBOOK_PAGENUMBERS and SPELLBOOK_PAGENUMBERS[index]
    end
    local current,maximum=read(SpellBook_GetCurrentPage)
    for index=1,12 do
        local button=_G['SpellButton'..index]
        if button and read(button.IsVisible,button) then
            local slot,kind,action=read(SpellBook_GetSpellBookSlot,button)
            local name,rank,id=read(GetSpellBookItemName,slot,book.bookType)
            local apiKind,apiID=read(GetSpellBookItemInfo,slot,book.bookType)
            local flyout
            if apiKind=='FLYOUT' then
                local flyoutName,_,count,isKnown=read(GetFlyoutInfo,apiID)
                flyout={id=apiID,name=flyoutName,count=count,known=isKnown,slots={}}
                for entry=1,math.min(tonumber(count) or 0,32) do
                    local spell,override,known,name=read(GetFlyoutSlotInfo,apiID,entry)
                    flyout.slots[#flyout.slots+1]={index=entry,id=spell,override=override,known=known,name=name}
                end
            end
            rows[#rows+1]={button=button:GetName(),slot=slot,kind=kind,action=action,flyout=flyout,
                api_kind=apiKind,api_id=apiID,name=name,rank=rank,id=id,
                shown_name=text(button.SpellName),shown_rank=text(button.SpellSubName),
                passive=not not button.isPassive,known=id and read(IsSpellKnown,id),
                trainer=button.TrainFrame and not not read(button.TrainFrame.IsVisible,button.TrainFrame) or false}
        end
    end
    local tooltip=Client442ObserveTooltip()
    tooltip.comparisons=nil
    while #tooltip.lines>6 do table.remove(tooltip.lines) end
    local flyout={visible=SpellFlyout and not not read(SpellFlyout.IsVisible,SpellFlyout) or false,buttons={}}
    if flyout.visible then
        local parent=read(SpellFlyout.GetParent,SpellFlyout)
        flyout.parent=parent and read(parent.GetName,parent)
        for index=1,32 do
            local button=_G['SpellFlyoutButton'..index]
            if button and read(button.IsVisible,button) then
                local info=C_Spell and read(C_Spell.GetSpellInfo,button.spellID)
                flyout.buttons[#flyout.buttons+1]={button=read(button.GetName,button),id=button.spellID,
                    name=read(GetSpellInfo,button.spellID) or info and info.name,
                    known=read(IsSpellKnown,button.spellID),enabled=read(button.IsEnabled,button)}
            end
        end
    end
    return {visible=book and not not read(book.IsVisible,book) or false,flyout=flyout,
        lifecycle=read(Client442ObserveSpellBookLifecycle),
        chat_link_dispatch=Client442CompatibilityStatus and Client442CompatibilityStatus.spell_chat_link_dispatch or false,
        book_type=book and book.bookType,skill_line=book and book.selectedSkillLine,
        book_types={spell=BOOKTYPE_SPELL,profession=BOOKTYPE_PROFESSION,pet=BOOKTYPE_PET},
        tabs=tabs,rows=rows,pages=pages,page=current,max_pages=maximum,
        page_text=text(SpellBookPageText),tooltip=tooltip,
        pet={exists=not not read(UnitExists,'pet'),guid=read(UnitGUID,'pet'),name=read(UnitName,'pet'),
            spells=read(GetNumPetSpells)},
        professions=book and book.bookType==BOOKTYPE_PROFESSION and Client442ObserveProfessions() or nil}
end
