-- Public read-only diagnostics. No talent/glyph selection or frame mutation.
local function call(fn,...)
    if type(fn)~='function' then return nil end
    local ok,a,b,c,d,e,f,g,h,i,j=pcall(fn,...)
    if ok then return a,b,c,d,e,f,g,h,i,j end
end
function Client442ObserveTalents()
    if not PlayerTalentFrame or not PlayerTalentFrame:IsVisible() then return nil end
    local group=call(GetActiveTalentGroup,false,false)
    local data={groups=call(GetNumTalentGroups),active=call(GetActiveTalentGroup),
        unspent=call(GetUnspentTalentPoints),selected=call(PanelTemplates_GetSelectedTab,PlayerTalentFrame),tabs={},glyphs={},frames={},
        primary=call(GetPrimaryTalentTree,false,false),preview_primary=call(GetPreviewPrimaryTalentTree,false,false),
        preview_option=call(GetCVarBool,'previewTalentsOption'),
        preview_spent=call(GetGroupPreviewTalentPointsSpent,false,call(GetActiveTalentGroup)),
        rank_columns={'tree','index','name','rank','max_rank','preview_rank'},ranks={},popups={}}
    for i=1,3 do
        local id,name,description,icon,spent,background,preview,unlocked=call(GetTalentTabInfo,i,false,false,group)
        data.tabs[#data.tabs+1]={id=id,name=name,spent=spent,background=background,unlocked=unlocked,
            count=call(GetNumTalents,i,false,false)}
        for j=1,(call(GetNumTalents,i,false,false) or 0) do
            local talentName,texture,tier,column,rank,maxRank,meetsPrereq,previewRank=call(GetTalentInfo,i,j,false,false,group)
            -- First-tier choices and allocated ranks suffice for the bounded
            -- learning trial without overflowing the screenshot payload.
            if tier==1 or (rank or 0)>0 or (previewRank or 0)>0 then
                data.ranks[#data.ranks+1]={i,j,talentName,rank,maxRank,previewRank}
            end
        end
    end
    for i=1,9 do
        local enabled,type_,tooltip,spell,icon,id=call(GetGlyphSocketInfo,i)
        data.glyphs[#data.glyphs+1]={index=i,enabled=enabled,type=type_,spell=spell,id=id}
    end
    for _,name in ipairs({'PlayerTalentFrame','PlayerTalentFrameInset','PlayerTalentFrameInsetBg','PlayerTalentFrameTalents',
        'PlayerTalentFramePanel1','PlayerTalentFramePanel2','PlayerTalentFramePanel3','GlyphFrame',
        'GlyphFrameBackground','GlyphFrameGlyph1','GlyphFrameGlyph2','GlyphFrameGlyph3','GlyphFrameGlyph4',
        'GlyphFrameGlyph5','GlyphFrameGlyph6','GlyphFrameGlyph7','GlyphFrameGlyph8','GlyphFrameGlyph9'}) do
        local f=_G[name]
        if f then data.frames[#data.frames+1]={name=name,visible=not not call(f.IsVisible,f),
            rect={call(f.GetRect,f)},scale=call(f.GetEffectiveScale,f),texture=call(f.GetTexture,f)} end
    end
    for i=1,3 do
        local f=_G['StaticPopup'..i]
        if f and f:IsVisible() then data.popups[#data.popups+1]={name=f:GetName(),which=f.which,
            text=tostring(f.text and call(f.text.GetText,f.text) or ''):sub(1,180)} end
    end
    return data
end
