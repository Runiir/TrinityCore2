-- Public action readiness and cast events. Never casts or selects a target.
local function call(fn,...)
    if type(fn)~='function' then return end
    local ok,a,b,c,d,e,f,g,h,i=pcall(fn,...)
    if ok then return a,b,c,d,e,f,g,h,i end
end
local gather={starts=0,successes=0}
local event=CreateFrame('Frame')
event:RegisterEvent('UNIT_SPELLCAST_START');event:RegisterEvent('UNIT_SPELLCAST_SUCCEEDED')
event:SetScript('OnEvent',function(_,kind,unit,_,spell)
    if unit~='player' or spell~=73979 then return end
    if kind=='UNIT_SPELLCAST_START' then gather.starts=gather.starts+1;gather.last_start=GetTime()
    elseif kind=='UNIT_SPELLCAST_SUCCEEDED' then gather.successes=gather.successes+1;gather.last_success=GetTime() end
end)
function WhitemaneLiveActivity()
    local bearings=CanopicHelperDB and CanopicHelperDB.surveyBearings
    local bearing=bearings and bearings[#bearings]
    local guidance
    if bearing and bearing.at and time()-bearing.at<=20 then
        guidance={at=bearing.at,site_id=bearing.siteID,color=bearing.color,
            candidate_matches=not not bearing.candidate,candidate_along_yards=bearing.candidateAlong,
            range_min_yards=bearing.rangeMin,range_max_yards=bearing.rangeMax,
            displayed_length_yards=bearing.length,minimum_capped=not not bearing.minimumCapped}
    end
    local current,run,flight,swim=call(GetUnitSpeed,'player')
    local action,id=call(GetActionInfo,1)
    local label=action=='spell' and call(GetSpellInfo,id) or action=='macro' and call(GetMacroInfo,id)
    local start,duration=call(GetActionCooldown,1)
    local usable=call(IsUsableAction,1)
    local health,maximum=call(UnitHealth,'target'),call(UnitHealthMax,'target')
    local name,_,_,castStart,castEnd,_,_,_,spell=call(UnitCastingInfo,'player')
    local channel=false
    if not name then
        name,_,_,castStart,castEnd=call(UnitChannelInfo,'player');channel=not not name
    end
    local gcdStart,gcdDuration=call(GetSpellCooldown,61304)
    local gcd=call(C_Spell and C_Spell.GetSpellCooldown,61304)
    if type(gcd)=='table' then gcdStart,gcdDuration=gcd.startTime,gcd.duration end
    local enemies=call(WhitemaneLiveCombatFacts) or {}
    return {activity_schema='whitemane_public_activity_v2',
        combat_facts_schema='observed_attackers_v1',
        move_speeds={current=current,run=run,flight=flight,swim=swim},gathering=gather,
        combat={target_exists=not not call(UnitExists,'target'),hostile=not not call(UnitCanAttack,'player','target'),
            target_engaged=enemies.target_engaged,attackers=enemies.attackers or {},
            target_guid=call(UnitGUID,'target'),target_name=call(UnitName,'target'),
            target_attacks_player=not not call(UnitIsUnit,'targettarget','player'),
            click_to_move=call(GetCVar,'autointeract'),
            target_dead=not not call(UnitIsDeadOrGhost,'target'),target_health=health,target_max_health=maximum,
            attack_label=label,attack_usable=not not usable,attack_in_range=call(IsActionInRange,1),
            cooldown_ends=(start or 0)+(duration or 0),energy=call(UnitPower,'player')},
        casting={name=name,starts=castStart and castStart/1000,ends=castEnd and castEnd/1000,
            channel=channel,spell=spell},
        gcd={starts=gcdStart or 0,duration=gcdDuration or 0,ends=(gcdStart or 0)+(gcdDuration or 0)},
        mount_binding={key='SHIFT-SPACE',action=call(GetBindingAction,'SHIFT-SPACE')},
        camera_input={right_down=call(IsMouseButtonDown,'RightButton'),mouselooking=call(IsMouselooking)},
        survey_guidance=guidance}
end
