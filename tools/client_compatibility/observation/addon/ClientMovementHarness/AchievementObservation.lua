-- Read-only stock categories, achievement rows and tracking state.
local function call(fn,...)
    if type(fn)~='function' then return nil end
    local ok,a,b,c,d,e,f,g,h,i,j,k,l,m,n=pcall(fn,...)
    if ok then return a,b,c,d,e,f,g,h,i,j,k,l,m,n end
end
local function text(region,n)
    return tostring(region and call(region.GetText,region) or ''):sub(1,n or 80)
end
function Client442ObserveAchievements()
    local frame=AchievementFrame
    if not frame or not frame:IsVisible() then return {visible=false} end
    local result={visible=true,tab=frame.selectedTab,
        category=achievementFunctions and achievementFunctions.selectedCategory,
        selection=AchievementFrameAchievements and AchievementFrameAchievements.selection,
        points=call(GetTotalAchievementPoints),tracked={call(GetTrackedAchievements)},categories={},rows={}}
    for _,button in ipairs(AchievementFrameCategoriesContainer and AchievementFrameCategoriesContainer.buttons or {}) do
        if button:IsVisible() and #result.categories<16 then
            result.categories[#result.categories+1]={id=button.categoryID,button=button:GetName(),
                text=text(button.label),selected=button.isSelected}
        end
    end
    for _,button in ipairs(AchievementFrameAchievementsContainer and AchievementFrameAchievementsContainer.buttons or {}) do
        if button:IsVisible() and button.id and #result.rows<6 then
            local id,name,points,completed,month,day,year,description,flags=call(GetAchievementInfo,button.id)
            local row={id=id,name=name,points=points,completed=not not completed,flags=flags,
                shown_name=text(button.label),description=text(button.description,140),button=button:GetName(),
                selected=not not button.selected,tracked=not not call(IsTrackedAchievement,button.id)}
            if button.tracked then row.tracking_button=button.tracked:GetName()
                row.tracking_visible=button.tracked:IsVisible();row.tracking_checked=button.tracked:GetChecked() end
            result.rows[#result.rows+1]=row
        end
    end
    return result
end
