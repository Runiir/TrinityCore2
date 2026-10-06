"""Initial sparse creation supplies zero defaults; foreign/update rows cannot."""
import json
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


def test_saved_stage_record_recovers_numeric_health_fields_without_changing_the_source():
    native={'guid':7,'kind':3,'map':0,'fields':{INDEX['UNIT_FIELD_HEALTH']:14,INDEX['UNIT_FIELD_MAXHEALTH']:14}}
    saved=json.loads(json.dumps(native));assert str(INDEX['UNIT_FIELD_HEALTH']) in saved['fields']
    assert run.load_target(saved)==native
    assert str(INDEX['UNIT_FIELD_HEALTH']) in saved['fields']


def test_saved_target_refuses_two_strings_for_one_native_field_number():
    with pytest.raises(ValueError):run.load_target({'fields':{'26':14,'026':0}})


def test_living_critter_native_stop_delivered_before_typed_stop_needs_no_duplicate_request():
    stops=[{'native':{'time':2.},'client':{'time':2.01}}]
    assert run.stop_request_contract(0,0,stops,3.)
    assert run.stop_request_contract(1,1,stops,3.)


@pytest.mark.parametrize('fault',['undelivered','too_late','reverse_time','missing','request_mismatch','duplicate'])
def test_zero_stop_request_requires_actual_delivery_before_stock_command_submission(fault):
    stops=[{'native':{'time':2.},'client':{'time':2.01}}];modern=native=0
    if fault=='undelivered':stops[0]['client']=None
    elif fault=='too_late':stops[0]['client']['time']=3.
    elif fault=='reverse_time':stops[0]['native']['time']=2.02
    elif fault=='missing':stops=[]
    elif fault=='request_mismatch':modern=1
    elif fault=='duplicate':modern=native=2
    assert not run.stop_request_contract(modern,native,stops,3.)
