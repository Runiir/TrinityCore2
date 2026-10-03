-- Stock Cata archaeology API/frame reads. No selection, solve or item mutations.
local function call(fn,...)
    if type(fn)~='function' then return nil end
    local ok,a,b,c,d,e,f,g,h,i,j=pcall(fn,...)
    if ok then return a,b,c,d,e,f,g,h,i,j end
end
local function text(frame)
    return frame and call(frame.GetText,frame)
end
function Client442ObserveArchaeology(page)
    local count=call(GetNumArchaeologyRaces) or 0
    local frame=ArchaeologyFrame
    local artifact=frame and frame.artifactPage
    local summary=frame and frame.summaryPage
    local solve=artifact and artifact.solveFrame
    local data={page=page,race_count=count,races={},visible=frame and not not call(frame.IsVisible,frame) or false,
        history_available=call(IsArtifactCompletionHistoryAvailable),
        summary_visible=summary and not not call(summary.IsVisible,summary) or false,
        summary_page=summary and summary.currentPage,
        artifact_visible=artifact and not not call(artifact.IsVisible,artifact) or false,
        selected_race=artifact and artifact.raceID,rendered_artifact=text(artifact and artifact.artifactName),
        rendered_progress=text(solve and solve.statusBar and solve.statusBar.text),
        solve_visible=solve and not not call(solve.IsVisible,solve) or false,
        solve_enabled=solve and solve.solveButton and not not call(solve.solveButton.IsEnabled,solve.solveButton) or false}
    local name,description,rarity,icon,spellDescription,sockets,background,spell=call(GetSelectedArtifactInfo)
    if name then data.selected={name=name,description=tostring(description or ''):sub(1,180),
        rarity=rarity,icon=icon,sockets=sockets,spell=spell} end
    local base,adjust,cost=call(GetArtifactProgress)
    data.progress={base=base,adjust=adjust,cost=cost,can_solve=call(CanSolveArtifact)}
    for index=(page-1)*4+1,math.min(page*4,count) do
        local race,texture,keystone,quantity,required=call(GetArchaeologyRaceInfo,index,false)
        local projects=call(GetNumArtifactsByRace,index) or 0
        local row={index=index,name=race,keystone=keystone,quantity=quantity,required=required,
            projects=projects,completed={}}
        for project=1,math.min(projects,200) do
            local title,_,rare,_,_,_,_,projectSpell,first,times=call(GetArtifactInfoByRace,index,project)
            if type(times)=='number' and times>0 then
                row.completed[#row.completed+1]={index=project,name=title,rarity=rare,spell=projectSpell,
                    first_completed=first,count=times}
            end
        end
        if summary and summary.currentPage then
            local slot=index-((summary.currentPage-1)*(ARCHAEOLOGY_MAX_RACES or 12))
            local button=slot>0 and summary['race'..slot]
            if button then row.button={name=button:GetName(),visible=not not call(button.IsVisible,button),
                enabled=not not call(button.IsEnabled,button),rendered=text(button.raceName)} end
        end
        data.races[#data.races+1]=row
    end
    return data
end
