from pathlib import Path
import subprocess


def test_saved_preference_changes_and_owned_event_bounds():
    source=Path(__file__).resolve().parents[2]/'observation/addon/ClientMovementHarness/CombatLogObservation.lua'
    script=r'''
local handler
function CreateFrame()
    local events={}
    return {RegisterEvent=function(_,event)events[event]=true end,
        IsEventRegistered=function(_,event)return events[event] or false end,
        SetScript=function(_,name,fn)handler=fn end}
end
function UnitGUID()return 'Player-1-00000001' end
ChatFrame2={GetNumMessages=function()return 0 end,IsVisible=function()return false end,
    GetMessageInfo=function()return nil end}
SELECTED_CHAT_FRAME={GetID=function()return 1 end}
local function config(reverse)
    local settings={}
    if reverse then settings.color=.5;settings.fullText=true
    else settings.fullText=true;settings.color=.5 end
    return {currentFilter=1,filters={{name='My actions',settings=settings,
        filters={{eventList={SPELL_CAST_SUCCESS=false,SPELL_DAMAGE=true},sourceFlags={[1]=true}}}}}}
end
Blizzard_CombatLog_Filters=config(false)
Blizzard_CombatLog_CurrentSettings=Blizzard_CombatLog_Filters.filters[1]
dofile(SOURCE)
local function fingerprint()return Client442ObserveCombatLog().saved_settings end
local initial=fingerprint();assert(initial.available)
Blizzard_CombatLog_Filters=config(true)
local ordered=fingerprint()
assert(initial.first==ordered.first and initial.second==ordered.second and initial.nodes==ordered.nodes)
Blizzard_CombatLog_Filters.filters[1].settings.color=.75
local changed=fingerprint();assert(changed.first~=initial.first or changed.second~=initial.second)
Blizzard_CombatLog_Filters=config(false)
Blizzard_CombatLog_Filters.filters[1].filters[1].eventList.SPELL_CAST_SUCCESS=true
changed=fingerprint();assert(changed.first~=initial.first or changed.second~=initial.second)
Blizzard_CombatLog_Filters.cycle=Blizzard_CombatLog_Filters
assert(not fingerprint().available)
Blizzard_CombatLog_Filters=config(false)
Blizzard_CombatLog_CurrentSettings=Blizzard_CombatLog_Filters.filters[1]
local values={};for index=1,14 do values[index]=0 end
values[2]='SPELL_CAST_SUCCESS';values[3]=false;values[4]='Player-1-00000002'
values[8]=UnitGUID();values[12]=6673;values[13]='Battle Shout'
C_CombatLog={GetCurrentEventInfo=function()return unpack(values) end}
handler(nil,'COMBAT_LOG_EVENT_UNFILTERED');assert(Client442ObserveCombatLog().event_sequence==0)
values[4]=UnitGUID();values[12]=6674
handler(nil,'COMBAT_LOG_EVENT_UNFILTERED');assert(Client442ObserveCombatLog().event_sequence==0)
values[12]=6673
for index=1,7 do handler(nil,'COMBAT_LOG_EVENT_UNFILTERED') end
local probe=Client442ObserveCombatLog()
assert(probe.event_registered and probe.unfiltered_registered)
assert(probe.event_sequence==7 and #probe.events==4)
assert(probe.events[1].sequence==4 and probe.events[4].sequence==7)
assert(probe.events[4].source_guid==UnitGUID() and probe.events[4].spell_id==6673)
assert(probe.events[4].dispatch=='COMBAT_LOG_EVENT_UNFILTERED')
'''
    subprocess.run(['lua','-'],input='SOURCE='+repr(str(source))+'\n'+script,
        text=True,capture_output=True,check=True)
