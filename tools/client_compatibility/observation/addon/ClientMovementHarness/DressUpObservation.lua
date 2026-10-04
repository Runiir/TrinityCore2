-- Passive stock model getters and post-call observation; never invokes TryOn.
local lastTryOn,hooked=nil,false
local function call(fn,...)
    if type(fn)~='function' then return nil end
    local ok,a=pcall(fn,...);if ok then return a end
end
function Client442ObserveDressUp()
    if not hooked and type(DressUpVisual)=='function' then
        hooked=true
        hooksecurefunc('DressUpVisual',function(link)
            lastTryOn={link=tostring(link or ''):sub(1,180),time=GetTime(),
                ctrl=not not IsControlKeyDown(),dressup=not not IsModifiedClick('DRESSUP')}
        end)
    end
    local model=DressUpModelFrame
    if not DressUpFrame or not DressUpFrame:IsVisible() or not model then return nil end
    return {visible=true,mode=DressUpFrame.mode,model_visible=model:IsVisible(),
        facing=call(model.GetFacing,model),geometry_ready=call(model.IsGeoReady,model),
        mainhand_appearance=call(model.GetItemModifiedAppearanceID,model,16),
        sheathed=call(model.GetSheathed,model),last_try_on=lastTryOn}
end
