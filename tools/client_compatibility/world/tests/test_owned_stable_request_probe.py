"""Only the expiring owned Erma GUID request enters a separate diagnostic journal."""
import json,time
import pytest
from tools.client_compatibility.world.buffer import Writer
from tools.client_compatibility.world.gameobjects import modern_guid
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result

MASTER=(0xf13<<52)|(6749<<32)|6109
BODY=Writer().guid(*modern_guid(MASTER,0)).finish()


def config():
    return {'schema':'client442_owned_stable_request_probe_v1','session':'fixture','owner':6,
        'native_master_guid':MASTER,'modern_master_guid':list(modern_guid(MASTER,0)),
        'created_at':100,'expires_at':120}


def probe(codec,tmp_path,c,body=BODY,direction='from_client',name='CMSG_REQUEST_STABLED_PETS',session='fixture',now=110):
    (tmp_path/'run').mkdir(exist_ok=True)
    (tmp_path/'run/owned_stable_request_probe.json').write_text(json.dumps(c))
    return result(codec,op='owned_stable_request_probe',root=str(tmp_path),direction=direction,name=name,
        session=session,now=now,body=body.hex())


def test_exact_public_stable_master_request(codec,tmp_path):
    assert probe(codec,tmp_path,config())
    assert not probe(codec,tmp_path,config(),session='another')
    assert not probe(codec,tmp_path,config(),direction='to_native')


@pytest.mark.parametrize('key,value',[('schema','other'),('session','foreign'),('owner',5),
    ('created_at',111),('expires_at',110),('expires_at',221),('native_master_guid',1),
    ('native_master_guid',(0xf13<<52)|(6749<<32)),('modern_master_guid',[1,2])])
def test_foreign_stale_or_unbounded_probe_cannot_capture(codec,tmp_path,key,value):
    c=config();c[key]=value;assert not probe(codec,tmp_path,c)


@pytest.mark.parametrize('body',[Writer().guid(1,2).finish(),BODY+b'private suffix',BODY[:-1],b''])
def test_other_identity_or_incomplete_packet_is_excluded(codec,tmp_path,body):
    assert not probe(codec,tmp_path,config(),body)


def test_absent_probe_and_authentication_are_excluded(codec,tmp_path):
    assert not result(codec,op='owned_stable_request_probe',root=str(tmp_path),direction='from_client',
        name='CMSG_REQUEST_STABLED_PETS',session='fixture',now=110,body=BODY.hex())
    assert not probe(codec,tmp_path,config(),name='CMSG_AUTH_SESSION')


def test_exact_capture_is_separate_from_global_packet_bodies(codec,tmp_path):
    c=config();c.update(created_at=time.time()-1,expires_at=time.time()+60)
    assert probe(codec,tmp_path,c,now=time.time())
    (tmp_path/'evidence').mkdir();(tmp_path/'logs').mkdir()
    result(codec,op='packet_diagnostic',root=str(tmp_path),name='CMSG_REQUEST_STABLED_PETS',body=BODY.hex())
    rows=[json.loads(line) for line in (tmp_path/'evidence/owned_stable_request_packets.jsonl').read_text().splitlines()]
    assert len(rows)==1 and rows[0]['body']==BODY.hex() and rows[0]['session']=='fixture'
    assert not (tmp_path/'evidence/world_packets.jsonl').exists()
