-- Public glyph catalog diagnostics. No selection, filtering or socket mutation.
local function call(fn,...)
    if type(fn)~='function' then return nil end
    local ok,a,b,c,d,e,f=pcall(fn,...)
    if ok then return a,b,c,d,e,f end
end
function Client442ObserveGlyphs(page)
    local total=call(GetNumGlyphs) or 0
    local data={total=total,page=page,rows={},filters={},sockets={},
        selected=call(GetSelectedGlyphSpellIndex),search=GlyphFrameSearchBox and call(GlyphFrameSearchBox.GetText,GlyphFrameSearchBox)}
    for i=(page-1)*12+1,math.min(total,page*12) do
        local name,type_,known,icon,id=call(GetGlyphInfo,i)
        data.rows[#data.rows+1]={index=i,name=name,type=type_,known=known,id=id}
    end
    for _,name in ipairs({'GLYPH_FILTER_KNOWN','GLYPH_FILTER_UNKNOWN','GLYPH_FILTER_PRIME','GLYPH_FILTER_MAJOR','GLYPH_FILTER_MINOR'}) do
        data.filters[#data.filters+1]={name=name,value=_G[name],active=call(IsGlyphFlagSet,_G[name])}
    end
    for i=1,9 do
        local enabled,type_,tooltip,spell,icon,id=call(GetGlyphSocketInfo,i)
        data.sockets[#data.sockets+1]={index=i,enabled=enabled,type=type_,spell=spell,id=id}
    end
    return data
end
