"""Dismiss evidence needs the exact owned native command and an actual disappearance."""
import copy,json,struct
from pathlib import Path
from types import SimpleNamespace
import pytest
from tools.client_compatibility import interaction_pet_dismiss as module
from tools.client_compatibility.world.objects import INDEX


@pytest.mark.parametrize('change',('none','missing_modern','duplicate_modern','missing_native','wrong_guid',
    'wrong_command','abandon','not_removed','summon_present','target_present','menu_open','lua_error','not_selected'))
def test_dismiss_cannot_pass_an_unmapped_foreign_or_incomplete_command(change):
    guid=0xf14001a000000008
    requests=[{'name':'CMSG_PET_ACTION','direction':'from_client','time':10,'body':'00'},
        {'name':'CMSG_PET_ACTION','direction':'to_native','time':10,
            'body':struct.pack('<QIQfff',guid,0x07000003,0,0,0,0).hex()}]
    state={'target':{'exists':False},'panels':[]}
    o=SimpleNamespace(requests=requests,removed={guid},player={INDEX['UNIT_FIELD_SUMMON']:0,INDEX['UNIT_FIELD_SUMMON']+1:0})
    if change=='missing_modern':requests.pop(0)
    elif change=='duplicate_modern':requests.append(copy.deepcopy(requests[0]))
    elif change=='missing_native':requests.pop()
    elif change=='wrong_guid':requests[1]['body']=struct.pack('<QIQfff',guid+1,0x07000003,0,0,0,0).hex()
    elif change=='wrong_command':requests[1]['body']=struct.pack('<QIQfff',guid,0x07000002,0,0,0,0).hex()
    elif change=='abandon':requests.append({'name':'CMSG_PET_ABANDON','time':10})
    elif change=='not_removed':o.removed.clear()
    elif change=='summon_present':o.player[INDEX['UNIT_FIELD_SUMMON']]=8
    elif change=='target_present':state['target']['exists']=True
    elif change=='menu_open':state['panels']=['ContextMenu']
    elif change=='lua_error':state['lua_errors']=['error']
    valid,_=module.dismiss_checks(o,guid,9,state,change!='not_selected')
    assert all(valid.values())==(change=='none')


def test_presence_accepts_native_destroy_and_a_new_owned_summon(tmp_path,monkeypatch):
    monkeypatch.setattr(module.lab,'ROOT',tmp_path)
    path=tmp_path/'evidence/world_packets.jsonl';path.parent.mkdir()
    golden=json.loads((Path(__file__).parent/'fixtures/native_pet_ui110.json').read_text())
    packets=[p['packet'] for p in golden['packets']]
    path.write_text(''.join(json.dumps(p)+'\n' for p in packets))
    o=module.Presence(packets[0]['session'],4,packets[0]['time']).poll()
    assert o.present();old=o.pet['guid'];new=old+1
    with path.open('a') as handle:handle.write(json.dumps({**packets[-1],'name':'SMSG_DESTROY_OBJECT',
        'body':struct.pack('<QB',old,0).hex(),'time':packets[-1]['time']+1})+'\n')
    assert not o.poll().present()
    pet=copy.deepcopy(o.pet);pet['guid']=new
    fields={INDEX['UNIT_FIELD_SUMMON']:new&0xffffffff,INDEX['UNIT_FIELD_SUMMON']+1:new>>32}
    monkeypatch.setattr(module,'records',lambda body:[pet,{'guid':4,'fields':fields}])
    with path.open('a') as handle:handle.write(json.dumps({**packets[-1],'body':'00','time':packets[-1]['time']+2})+'\n')
    assert o.poll().present() and o.pet['guid']==new
