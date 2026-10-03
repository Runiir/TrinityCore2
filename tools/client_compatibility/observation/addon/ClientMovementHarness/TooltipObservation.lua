-- Read the stock tooltip after ordinary mouse movement. No tooltip setters.
local function call(f,...)
    if type(f)~='function' then return end
    local ok,a,b=pcall(f,...);if ok then return a,b end
end
local function text(frame,limit)
    local value=frame and call(frame.GetText,frame)
    return type(value)=='string' and value:sub(1,limit) or nil
end
local function observe(tip,prefix)
    local visible=tip and not not call(tip.IsVisible,tip) or false
    local owner=tip and call(tip.GetOwner,tip)
    local name,link=tip and call(tip.GetItem,tip)
    if tip then name,link=call(tip.GetItem,tip) end
    local spell,id
    if tip then spell,id=call(tip.GetSpell,tip) end
    local data={visible=visible,owner=owner and call(owner.GetName,owner),
        item_name=name,item_link=link,spell_name=spell,spell_id=id,lines={}}
    if visible then
        data.line_count=call(tip.NumLines,tip) or 0
        for i=1,math.min(data.line_count,16) do
            data.lines[#data.lines+1]={left=text(_G[prefix..'TextLeft'..i],160),
                right=text(_G[prefix..'TextRight'..i],60)}
        end
    end
    return data
end
function Client442ObserveTooltip()
    local data=observe(GameTooltip,'GameTooltip')
    data.comparisons={observe(ShoppingTooltip1,'ShoppingTooltip1'),observe(ShoppingTooltip2,'ShoppingTooltip2')}
    data.shift_down=not not call(IsShiftKeyDown)
    data.always_compare=call(GetCVarBool,'alwaysCompareItems')
    return data
end
