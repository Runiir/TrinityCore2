"""Retained wire creation, sparse health and visibility loss stay attributable."""
import copy,json
from pathlib import Path
import pytest
from tools.client_compatibility import interaction_pet_target as module
from tools.client_compatibility.world.objects import INDEX


def oracle(tmp_path,monkeypatch):
    monkeypatch.setattr(module.lab,'ROOT',tmp_path)
    path=tmp_path/'evidence/world_packets.jsonl';path.parent.mkdir()
    golden=json.loads((Path(__file__).parent/'fixtures/native_pet_ui110.json').read_text())
    packets=[p['packet'] for p in golden['packets']]
    path.write_text(''.join(json.dumps(p)+'\n' for p in packets))
    return module.PetOracle(packets[0]['session'],4,packets[0]['time']),path,packets


def test_captured_owned_create_and_player_summon_agree(tmp_path,monkeypatch):
    o,_,_=oracle(tmp_path,monkeypatch);o.poll()
    assert o.pet['guid']==0xf14001a000000001
    assert module.pair(o.player,'UNIT_FIELD_SUMMON')==o.pet['guid']
    # The retained trace creates at140, then applies a later effective-stat update.
    assert o.pet['fields'][INDEX['UNIT_FIELD_HEALTH']]==254
    assert o.pet['fields'][INDEX['UNIT_FIELD_MAXHEALTH']]==254


@pytest.mark.parametrize('change',('session','before_entry','direction','owner'))
def test_wrong_session_time_direction_or_owner_cannot_supply_pet(tmp_path,monkeypatch,change):
    o,path,packets=oracle(tmp_path,monkeypatch)
    if change=='owner':
        original=module.records
        def wrong_owner(body):
            rows=original(body)
            for r in rows:
                if r.get('kind')==3 and r['guid']>>52==0xf14:r['fields'][INDEX['UNIT_FIELD_SUMMONEDBY']]=5
            return rows
        monkeypatch.setattr(module,'records',wrong_owner)
    else:
        for p in packets:
            if change=='session':p['session']='foreign'
            elif change=='before_entry':p['time']=0
            else:p['direction']='to_client'
        path.write_text(''.join(json.dumps(p)+'\n' for p in packets))
    assert o.poll().pet is None


@pytest.mark.parametrize('change',('sparse_health','ambiguous','removed'))
def test_later_sparse_update_or_visibility_change_is_preserved(tmp_path,monkeypatch,change):
    o,path,packets=oracle(tmp_path,monkeypatch);o.poll();pet=copy.deepcopy(o.pet)
    if change=='sparse_health':r={'update_type':0,'guid':pet['guid'],'fields':{INDEX['UNIT_FIELD_HEALTH']:120}}
    elif change=='ambiguous':r={**pet,'guid':pet['guid']+1}
    else:r={'update_type':3,'removed':[pet['guid']]}
    monkeypatch.setattr(module,'records',lambda body:[r])
    with path.open('a') as handle:handle.write(json.dumps({**packets[-1],'body':'00','time':packets[-1]['time']+1})+'\n')
    if change=='sparse_health':assert o.poll().pet['fields'][INDEX['UNIT_FIELD_HEALTH']]==120
    else:
        with pytest.raises(RuntimeError):o.poll()


@pytest.mark.parametrize('change',('none','public_power','public_type','missing_type','foreign_pet','foreign_owner',
    'summon_pointer','empty_target','hidden','lua_error','blocked','missing_native_type','sparse_power'))
def test_owned_mana_requires_exact_current_native_and_public_identity(tmp_path,monkeypatch,change):
    o,_,_=oracle(tmp_path,monkeypatch);o.poll();pet=o.pet;fields=pet['fields']
    o.player[INDEX['UNIT_FIELD_TARGET']]=pet['guid']&0xffffffff
    o.player[INDEX['UNIT_FIELD_TARGET']+1]=pet['guid']>>32
    native_power=fields[INDEX['UNIT_FIELD_POWER1']];maximum=fields[INDEX['UNIT_FIELD_MAXPOWER1']]
    assert native_power==maximum==155
    state={'target':{'guid':'current-owned-imp','visible':True}}
    public={'exists':True,'guid':'current-owned-imp','power':native_power,'max_power':maximum,'power_type':0}
    if change=='public_power':public['power']-=1
    elif change=='public_type':public['power_type']=2
    elif change=='missing_type':public.pop('power_type')
    elif change=='foreign_pet':public['guid']='other-pet'
    elif change=='foreign_owner':fields[INDEX['UNIT_FIELD_SUMMONEDBY']]=5
    elif change=='summon_pointer':o.player[INDEX['UNIT_FIELD_SUMMON']]+=1
    elif change=='empty_target':o.player[INDEX['UNIT_FIELD_TARGET']]=0;o.player[INDEX['UNIT_FIELD_TARGET']+1]=0
    elif change=='hidden':state['target']['visible']=False
    elif change=='lua_error':state['lua_errors']=['error']
    elif change=='blocked':state['blocked_actions']=['blocked']
    elif change=='missing_native_type':fields.pop(INDEX['UNIT_FIELD_BYTES_0'])
    elif change=='sparse_power':fields[INDEX['UNIT_FIELD_POWER1']]=120;public['power']=120
    checks,native=module.power_checks(o,state,public,'current-owned-imp')
    assert all(checks.values())==(change in ('none','sparse_power'))
    assert native['power']==(120 if change=='sparse_power' else 155)
