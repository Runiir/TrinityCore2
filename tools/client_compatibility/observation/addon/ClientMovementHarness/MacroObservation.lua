-- Public macro editor getters only; no macro, binding or action mutations.
local function call(fn,...)
    if type(fn)~='function' then return nil end
    local ok,a,b,c=pcall(fn,...)
    if ok then return a,b,c end
end

function Client442ObserveMacros()
    local frame=MacroFrame
    local data={open=frame and not not call(frame.IsVisible,frame) or false,
        counts={GetNumMacros()},account_limit=MAX_ACCOUNT_MACROS,character_limit=MAX_CHARACTER_MACROS}
    if not data.open then return data end
    data.tab=call(PanelTemplates_GetSelectedTab,frame)
    data.base=frame.macroBase;data.limit=frame.macroMax
    data.selected_index=call(frame.GetSelectedIndex,frame)
    if data.selected_index then
        data.actual_index=call(frame.GetMacroDataIndex,frame,data.selected_index)
        if data.actual_index then
            local name,icon,body=call(GetMacroInfo,data.actual_index)
            data.selected={name=name,icon=icon,body=type(body)=='string' and body:sub(1,255) or body,
                body_truncated=type(body)=='string' and #body>255 or false}
        end
    end
    local popup=MacroPopupFrame
    data.popup={visible=popup and not not call(popup.IsVisible,popup) or false,
        mode=popup and popup.mode}
    return data
end
