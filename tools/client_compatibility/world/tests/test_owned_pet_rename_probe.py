"""Synthetic rename diagnostics never broaden the global name-body journal."""
import json,time
import pytest
from tools.client_compatibility.world.buffer import Writer
from tools.client_compatibility.world.gameobjects import modern_guid
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result

PET=(0xf14<<52)|(42717<<32)|76


def config():
    return {'schema':'client442_owned_pet_rename_probe_v1','session':'fixture','owner':6,'pet_number':4,
        'synthetic_name':'Harnesswolf','native_pet_guid':PET,'modern_pet_guid':list(modern_guid(PET,0)),
        'created_at':100,'expires_at':120}


def request(*,number=4,name='Harnesswolf',declined=0,guid=None):
    return Writer().guid(*(guid or modern_guid(PET,0))).pack('i',number).bits(len(name),8).bits(declined,1).flush().raw(name.encode()).finish()


def probe(codec,tmp_path,c,body=None,direction='from_client',name='CMSG_PET_RENAME',session='fixture',now=110):
    (tmp_path/'run').mkdir(exist_ok=True)
    (tmp_path/'run/owned_pet_rename_probe.json').write_text(json.dumps(c))
    return result(codec,op='owned_pet_rename_probe',root=str(tmp_path),direction=direction,name=name,
        session=session,now=now,body=(body if body is not None else request()).hex())


def test_exact_synthetic_client_and_native_forms_only(codec,tmp_path):
    assert probe(codec,tmp_path,config())
    native=Writer().pack('Q',PET).raw(b'Harnesswolf\0\0').finish()
    assert probe(codec,tmp_path,config(),native,'to_native')
    assert not probe(codec,tmp_path,config(),native+b'private suffix','to_native')
    assert not probe(codec,tmp_path,config(),native[:-1],'to_native')


@pytest.mark.parametrize('key,value',[('schema','other'),('session','foreign'),('owner',5),('pet_number',2),
    ('synthetic_name','Arealname'),('created_at',111),('expires_at',110),('expires_at',221),
    ('native_pet_guid',1),('modern_pet_guid',[1,2])])
def test_foreign_stale_or_unbounded_probe_cannot_retain_a_name(codec,tmp_path,key,value):
    c=config();c[key]=value;assert not probe(codec,tmp_path,c)


@pytest.mark.parametrize('body',[request(number=2),request(name='Privatename'),request(declined=1),
    request(guid=(1,2)),request()+b'private suffix',request()[:-1],b''])
def test_other_pet_names_numbers_declensions_or_incomplete_shapes_are_excluded(codec,tmp_path,body):
    assert not probe(codec,tmp_path,config(),body)


def test_absent_probe_and_authentication_are_excluded(codec,tmp_path):
    assert not result(codec,op='owned_pet_rename_probe',root=str(tmp_path),direction='from_client',
        name='CMSG_PET_RENAME',session='fixture',now=110,body=request().hex())
    assert not probe(codec,tmp_path,config(),name='CMSG_AUTH_SESSION')
    assert not probe(codec,tmp_path,config(),direction='from_native')


def test_explicit_synthetic_capture_uses_separate_journal(codec,tmp_path):
    c=config();c.update(created_at=time.time()-1,expires_at=time.time()+60)
    assert probe(codec,tmp_path,c,now=time.time())
    (tmp_path/'evidence').mkdir();(tmp_path/'logs').mkdir()
    result(codec,op='packet_diagnostic',root=str(tmp_path),name='CMSG_PET_RENAME',body=request().hex())
    rows=[json.loads(line) for line in (tmp_path/'evidence/owned_pet_rename_packets.jsonl').read_text().splitlines()]
    assert len(rows)==1 and rows[0]['body']==request().hex() and rows[0]['session']=='fixture'
    assert not (tmp_path/'evidence/world_packets.jsonl').exists()
