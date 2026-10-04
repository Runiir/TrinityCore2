-- Read public profession APIs and already-rendered stock frames; no setters.
local function read(fn,...)
    if type(fn)~='function' then return nil end
    local ok,a,b,c,d,e,f,g,h,i,j,k=pcall(fn,...)
    if ok then return a,b,c,d,e,f,g,h,i,j,k end
end
local function shown(frame)
    return frame and not not read(frame.IsVisible,frame) or false
end
local function text(frame)
    local value=frame and read(frame.GetText,frame)
    return type(value)=='string' and value:sub(1,96) or nil
end
function Client442ObserveProfessions()
    local a,b,c,d,e,f=read(GetProfessions)
    local indices={a or false,b or false,c or false,d or false,e or false,f or false}
    local names={'PrimaryProfession1','PrimaryProfession2','SecondaryProfession1',
        'SecondaryProfession2','SecondaryProfession3','SecondaryProfession4'}
    local rows={}
    for slot=1,6 do
        local frame=_G[names[slot]]
        local row={frame=names[slot],slot=slot,index=indices[slot],visible=shown(frame)}
        if indices[slot] then
            local name,texture,rank,maxRank,count,offset,skill,modifier,spec,specOffset,skillName=
                read(GetProfessionInfo,indices[slot])
            row.api={name=name,rank=rank,max_rank=maxRank,count=count,offset=offset,
                skill=skill,modifier=modifier,spec=spec,spec_offset=specOffset,skill_name=skillName}
        end
        if frame then
            local bar=frame.statusBar
            local minimum,maximum
            if bar then minimum,maximum=read(bar.GetMinMaxValues,bar) end
            row.rendered={name=text(frame.professionName),rank=text(frame.rank),
                skill=frame.skillLine,rank_text=bar and text(bar.rankText),
                bar_visible=shown(bar),bar_min=minimum,bar_max=maximum,
                bar_value=bar and read(bar.GetValue,bar),
                missing_header_visible=shown(frame.missingHeader),missing_text_visible=shown(frame.missingText),
                missing_header=text(frame.missingHeader),missing_text=text(frame.missingText)}
            row.buttons={}
            for index=1,2 do
                local button=frame['SpellButton'..index]
                if shown(button) then
                    local spellSlot=read(button.GetID,button)+(frame.spellOffset or 0)
                    local name,rank,id=read(GetSpellBookItemName,spellSlot,BOOKTYPE_PROFESSION)
                    row.buttons[#row.buttons+1]={button=button:GetName(),slot=spellSlot,name=name,id=id,
                        shown_name=text(button.spellString),known=id and read(IsSpellKnown,id)}
                end
            end
        end
        rows[#rows+1]=row
    end
    return rows
end
