"""Real native ground chase, stop, and facing splines in the 60895 layout."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from tools.client_compatibility.world import creature_movement as movement
from tools.client_compatibility.world.buffer import Reader
from tools.client_compatibility.world.gameobjects import modern_guid


@pytest.mark.parametrize('captured',json.loads((Path(__file__).parent/'fixtures/creature_splines.json').read_text()))
def test_captured_spline_retains_path_duration_stop_and_facing(captured):
    native=bytes.fromhex(captured['body']);s=movement.parse(native)
    owner=SimpleNamespace(visible_units={s['guid']:{'map':530,'movement':{'position':[0,0,0,0],'time':1234}}})
    name,body=movement.response(owner,'SMSG_ON_MONSTER_MOVE',native);r=Reader(body)
    assert name=='SMSG_ON_MONSTER_MOVE' and r.guid()==modern_guid(s['guid'],530)
    assert list(r.unpack('3f'))==s['position'] and r.unpack('I')==(s['sequence'],)
    assert r.bits(4)==0
    assert r.unpack('IIIIB')==(s['flags'],0,s['duration'],0,0)
    assert r.guid()==(0,0) and r.unpack('b')==(-1,)
    face=r.bits(2);assert face=={0:0,1:0,2:1,3:2,4:3}[s['face']]
    assert r.bits(16)==len(s['points']);assert r.bits(1)==s['exit_voluntary'];assert r.bits(1)==0
    assert r.bits(16)==len(s['deltas'])//4;assert r.bits(4)==0
    if face==1:assert r.unpack('3f')==s['facing']
    if face==2:assert r.unpack('f')==(0,) and r.guid()==modern_guid(s['facing'],530)
    if face==3:assert r.unpack('f')==(s['facing'],)
    assert [list(r.unpack('3f')) for _ in s['points']]==s['points']
    assert r.raw(len(s['deltas']))==s['deltas'];r.end()
    if s['face']==1:assert s['flags']&0x20 and not s['points']
    assert movement.response(SimpleNamespace(visible_units={}),name,native) is None
    r=Reader(movement.position_update(owner,native))
    assert r.guid()==modern_guid(s['guid'],530)
    assert r.unpack('IIII')==(0,0,0,1234)
    assert list(r.unpack('3f'))==s['position']
    assert r.unpack('3fII')==(0,0,0,0,s['sequence']) and r.bits(8)==0;r.end()
