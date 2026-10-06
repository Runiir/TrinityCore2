-- Read the stock /m window. All creation/editing remains normal actor UI input.
function WhitemaneLiveMacroUI(control,append,visible,text)
    local function call(fn,...)
        if type(fn)~='function' then return end
        local ok,a,b,c=pcall(fn,...);if ok then return a,b,c end
    end
    local frame,popup=MacroFrame,MacroPopupFrame
    local index=call(GetMacroIndexByName,'ArchaeologyView') or 0
    local name,icon,body
    if index>0 then name,icon,body=call(GetMacroInfo,index) end
    local result={schema='stock_macro_ui_v1',visible=not not visible(frame),
        popup_visible=not not visible(popup),controls={},
        installed={index=index,name=name,body=body,character=index>(MAX_ACCOUNT_MACROS or 120)}}
    if not result.visible then return result end
    result.character_tab=frame.macroBase and frame.macroBase>0 or frame.selectedTab==2
    result.selected_name=text(MacroFrameSelectedMacroName)
    local edit=MacroFrameText
    result.body=control(edit,'Macro commands',{kind='body',
        value=call(edit and edit.GetText,edit),focused=not not call(edit and edit.HasFocus,edit)})
    local border=popup and popup.BorderBox
    local entry=border and border.IconSelectorEditBox or MacroPopupEditBox
    result.name=control(entry,'New macro name',{kind='name',
        value=call(entry and entry.GetText,entry),focused=not not call(entry and entry.HasFocus,entry)})
    for _,item in ipairs({{'MacroFrameTab1','General macros','general'},
        {'MacroFrameTab2','Character macros','character'}, {'MacroNewButton','New macro','new'},
        {'MacroFrameSaveButton','Save macro','save'}, {'MacroFrameCloseButton','Close macros','close'}}) do
        append(result.controls,control(_G[item[1]],item[2],{kind=item[3]}))
    end
    append(result.controls,control(frame.CloseButton,'Close macros',{kind='close'}))
    local seen={}
    local function scan(parent,depth)
        if depth>7 or not visible(parent) then return end
        local kind=call(parent.GetObjectType,parent)
        local label=text(parent) or text(parent.Name) or text(parent.Text)
        if kind=='Button' and label=='ArchaeologyView' then
            append(result.controls,control(parent,label,{kind='select'}))
        elseif kind=='Button' and visible(popup) and (label=='Okay' or label=='OK' or label=='Accept') then
            local row=control(parent,'Create named macro',{kind='accept'})
            if row and not seen[parent] then append(result.controls,row);seen[parent]=true end
        end
        if parent.GetChildren then for _,child in ipairs({parent:GetChildren()}) do scan(child,depth+1) end end
    end
    scan(frame,0)
    return result
end
