"""Raw Abandon capture is confined to the disposable owned Wolf6."""
import json,struct
import pytest
from tools.client_compatibility.world.buffer import Writer
from tools.client_compatibility.world.gameobjects import modern_guid
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result

PET=(0xf14<<52)|(299<<32)|4
BODY=Writer().guid(*modern_guid(PET,0)).finish()


def config():
    return {'schema':'client442_owned_pet_abandon_probe_v1','owner':6,'pet_number':6,'session':'fixture',
        'native_pet_guid':PET,'modern_pet_guid':list(modern_guid(PET,0)),'created_at':100,'expires_at':190}


def probe(codec,tmp_path,c,body=BODY,direction='from_client',name='CMSG_PET_ABANDON',session='fixture',now=110):
    (tmp_path/'run').mkdir(exist_ok=True)
    (tmp_path/'run/owned_pet_abandon_probe.json').write_text(json.dumps(c))
    return result(codec,op='owned_pet_abandon_probe',root=str(tmp_path),direction=direction,name=name,
        session=session,now=now,body=body.hex())


def test_exact_owned_disposable_pet_guid_forms_only(codec,tmp_path):
    assert probe(codec,tmp_path,config())
    assert probe(codec,tmp_path,config(),struct.pack('<Q',PET),'to_native')
    assert not probe(codec,tmp_path,config(),BODY+b'x')
    assert not probe(codec,tmp_path,config(),BODY[:-1])


@pytest.mark.parametrize('field,value',[('schema','other'),('owner',5),('pet_number',4),('session','foreign'),
    ('native_pet_guid',(0xf14<<52)|(42717<<32)|4),('modern_pet_guid',[1,2]),
    ('created_at',111),('expires_at',110),('expires_at',191)])
def test_foreign_named_pet_or_stale_unbounded_capture_rejected(codec,tmp_path,field,value):
    c=config();c[field]=value;assert not probe(codec,tmp_path,c)


def test_authentication_and_foreign_direction_are_never_captured(codec,tmp_path):
    assert not probe(codec,tmp_path,config(),name='CMSG_AUTH_SESSION')
    assert not probe(codec,tmp_path,config(),direction='from_native')
    assert not probe(codec,tmp_path,config(),session='foreign')
