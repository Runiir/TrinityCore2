"""Passive stock swing observations retain only attributable owned results."""
from pathlib import Path
import subprocess


def test_owned_damage_miss_bounds_and_public_reader():
    source=Path(__file__).resolve().parents[2]/'observation/addon/ClientMovementHarness/MeleeObservation.lua'
    script=r'''
local handler,registered
function CreateFrame()return {RegisterEvent=function(_,event)registered=event end,
    SetScript=function(_,name,fn)handler=fn end} end
function UnitGUID()return 'Player-1-00000005' end
function IsCurrentSpell(spell)assert(spell==6603);return true end
dofile(SOURCE)
local values={123,'SWING_DAMAGE',false,UnitGUID(),'Harnessctrl',0,0,'Creature-0-1-0-0-44548-000002C181','Dummy',0,0,
    6,-1,1,0,0,0,false,false,false,false}
C_CombatLog={GetCurrentEventInfo=function()return unpack(values) end}
values[4]='Player-1-00000001';handler(nil,'COMBAT_LOG_EVENT_UNFILTERED')
assert(Client442ObserveMelee().event_sequence==0)
values[4]=UnitGUID();values[2]='SPELL_DAMAGE';handler(nil,'COMBAT_LOG_EVENT_UNFILTERED')
assert(Client442ObserveMelee().event_sequence==0)
values[2]='SWING_DAMAGE'
for i=1,7 do values[1]=i;handler(nil,'COMBAT_LOG_EVENT_UNFILTERED') end
local probe=Client442ObserveMelee();assert(probe.event_registered and probe.active)
assert(registered=='COMBAT_LOG_EVENT_UNFILTERED' and probe.event_sequence==7 and #probe.events==4)
local row=probe.events[4]
assert(row.source_guid==UnitGUID() and row.destination_guid==values[8])
assert(row.amount==6 and row.overkill==-1 and row.school==1 and not row.critical and not row.offhand)
assert(row.reader=='C_CombatLog.GetCurrentEventInfo' and row.dispatch=='COMBAT_LOG_EVENT_UNFILTERED')
values[2]='SWING_MISSED';values[12]='DODGE';values[13]=true;values[14]=6
handler(nil,'COMBAT_LOG_EVENT_UNFILTERED');row=Client442ObserveMelee().events[4]
assert(row.miss_type=='DODGE' and row.offhand and row.amount_missed==6 and row.amount==nil)
C_CombatLog=nil
CombatLogGetCurrentEventInfo=function()return unpack(values) end
handler(nil,'COMBAT_LOG_EVENT_UNFILTERED')
assert(Client442ObserveMelee().events[4].reader=='CombatLogGetCurrentEventInfo')
CombatLogGetCurrentEventInfo=function()error('not available') end
local count=Client442ObserveMelee().event_sequence
handler(nil,'COMBAT_LOG_EVENT_UNFILTERED');assert(Client442ObserveMelee().event_sequence==count)
'''
    subprocess.run(['lua','-'],input='SOURCE='+repr(str(source))+'\n'+script,
        text=True,capture_output=True,check=True)
