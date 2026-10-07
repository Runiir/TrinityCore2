"""Stock channel events remain passive, attributable and bounded across stop."""
from pathlib import Path
import shutil,subprocess
import pytest


def test_passive_channel_reader_keeps_actual_start_and_stop_without_casting():
    lua=shutil.which('lua')
    if not lua:pytest.skip('Lua interpreter unavailable')
    source=Path(__file__).resolve().parents[2]/'observation/addon/ClientMovementHarness/SpellChannelObservation.lua'
    script="""
local handler,name,registered=nil,nil,{}
function CreateFrame(kind)
 assert(kind=='Frame');return {RegisterEvent=function(_,event)registered[event]=true end,
 SetScript=function(_,event,callback)assert(event=='OnEvent');handler=callback end}
end
function CastSpell()error('reader must not cast')end
function CastSpellByID()error('reader must not cast')end
function UnitChannelInfo(unit)assert(unit=='player');return name end
function GetTime()return 42 end
dofile(arg[1])
assert(registered.UNIT_SPELLCAST_CHANNEL_START and registered.UNIT_SPELLCAST_CHANNEL_STOP)
assert(not Client442ObserveSpellChannel().active)
handler(nil,'UNIT_SPELLCAST_CHANNEL_START','target','foreign',1515)
assert(Client442ObserveSpellChannel().event_sequence==0)
name='Tame Beast';handler(nil,'UNIT_SPELLCAST_CHANNEL_START','player','actual',1515)
local state=Client442ObserveSpellChannel()
assert(state.active and state.name=='Tame Beast' and state.events[1].spell==1515)
assert(state.events[1].channel.name=='Tame Beast' and state.events[1].cast_id=='actual')
name=nil;handler(nil,'UNIT_SPELLCAST_CHANNEL_STOP','player','actual',1515)
state=Client442ObserveSpellChannel();assert(not state.active and not state.events[2].channel.active)
for i=1,5 do handler(nil,'UNIT_SPELLCAST_CHANNEL_UPDATE','player','actual',1515) end
state=Client442ObserveSpellChannel();assert(state.event_sequence==7 and #state.events==4)
assert(state.events[1].sequence==4 and state.events[4].sequence==7)
"""
    subprocess.run([lua,'-',str(source)],input=script,text=True,check=True,capture_output=True,timeout=3)
