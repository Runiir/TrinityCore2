"""Initial sparse creation supplies zero defaults; foreign/update rows cannot."""
import pytest
from tools.client_compatibility import interaction_owned_melee_health as run
from tools.client_compatibility.world.objects import INDEX


@pytest.mark.parametrize('value',[None,0,0x100])
def test_initial_owned_player_creation_preserves_explicit_or_zero_default_pvp(monkeypatch,value):
    fields={} if value is None else {INDEX['UNIT_FIELD_BYTES_2']:value}
    packet={'session':'s','direction':'from_native','name':'SMSG_UPDATE_OBJECT','time':2.,'body':'00'}
    monkeypatch.setattr(run,'entries',lambda _:iter([packet]))
    monkeypatch.setattr(run,'records',lambda _:[{'kind':4,'guid':5,'fields':fields}])
    result=run.entry_pvp('s',{'started_at':1.,'finished_at':3.})
    assert result['value']==(value or 0) and result['zero_default_from_creation']==(value is None)


@pytest.mark.parametrize('fault',['foreign_actor','update_only','foreign_session','outside_entry'])
def test_initial_pvp_proof_refuses_other_actors_updates_and_lifetimes(monkeypatch,fault):
    packet={'session':'s','direction':'from_native','name':'SMSG_UPDATE_OBJECT','time':2.,'body':'00'}
    row={'kind':4,'guid':5,'fields':{}}
    if fault=='foreign_actor':row['guid']=6
    elif fault=='update_only':row.pop('kind')
    elif fault=='foreign_session':packet['session']='another'
    elif fault=='outside_entry':packet['time']=4.
    monkeypatch.setattr(run,'entries',lambda _:iter([packet]));monkeypatch.setattr(run,'records',lambda _:[row])
    with pytest.raises(RuntimeError):run.entry_pvp('s',{'started_at':1.,'finished_at':3.})
