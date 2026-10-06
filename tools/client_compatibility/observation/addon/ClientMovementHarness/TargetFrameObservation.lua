-- Read the visible stock target frame; never invoke a unit or menu action.
local function read(fn,...)
    if type(fn)~='function' then return nil end
    local ok,value=pcall(fn,...)
    if ok then return value end
end

-- PetFrame has asymmetric hit insets: its visual center hits PlayerFrame.
-- Read the center of its actual mouse rectangle without changing the frame.
function Client442ObservePetFrame()
    local frame=PetFrame
    if not frame or not read(frame.IsVisible,frame) or not read(frame.IsMouseEnabled,frame) or
        frame.IsEnabled and not read(frame.IsEnabled,frame) then return nil end
    local unit=read(frame.GetAttribute,frame,'unit') or frame.unit
    local guid=unit=='pet' and read(UnitGUID,unit)
    if not guid or type(frame.GetHitRectInsets)~='function' then return nil end
    local ok,left,right,top,bottom=pcall(frame.GetHitRectInsets,frame)
    local x,y=frame:GetCenter()
    local w,h=read(frame.GetWidth,frame),read(frame.GetHeight,frame)
    if not ok or not x or not y or not w or not h or
        type(left)~='number' or type(right)~='number' or type(top)~='number' or type(bottom)~='number' or
        left<0 or right<0 or top<0 or bottom<0 or left+right>=w or top+bottom>=h then return nil end
    x=x+(left-right)/2;y=y+(bottom-top)/2
    local scale=read(frame.GetEffectiveScale,frame)
    local parentScale=UIParent and read(UIParent.GetEffectiveScale,UIParent)
    local width,height=GetScreenWidth(),GetScreenHeight()
    if not scale or not parentScale or width<=0 or height<=0 or parentScale<=0 then return nil end
    x=math.floor(x*scale/(width*parentScale)*65535)
    y=math.floor((1-y*scale/(height*parentScale))*65535)
    if x<=0 or x>=65535 or y<=0 or y>=65535 then return nil end
    return {name=read(frame.GetName,frame),unit=unit,guid=guid,x=x,y=y,visible=true,enabled=true,
        point_basis='hit_rectangle_center',hit_insets={left,right,top,bottom}}
end

function Client442ObserveTargetFrame()
    local frame=TargetFrame
    if not frame or not read(frame.IsVisible,frame) then return nil end
    local unit=read(frame.GetAttribute,frame,'unit') or frame.unit
    local guid=unit=='target' and read(UnitGUID,unit)
    if not guid or not read(frame.IsMouseEnabled,frame) or
        frame.IsEnabled and not read(frame.IsEnabled,frame) then return nil end
    local x,y=frame:GetCenter()
    local scale=read(frame.GetEffectiveScale,frame)
    local parentScale=UIParent and read(UIParent.GetEffectiveScale,UIParent)
    local width,height=GetScreenWidth(),GetScreenHeight()
    if not x or not y or not scale or not parentScale or width<=0 or height<=0 or parentScale<=0 then return nil end
    x=math.floor(x*scale/(width*parentScale)*65535)
    y=math.floor((1-y*scale/(height*parentScale))*65535)
    if x<=0 or x>=65535 or y<=0 or y>=65535 then return nil end
    return {name=read(frame.GetName,frame),unit=unit,guid=guid,x=x,y=y,visible=true,enabled=true}
end
