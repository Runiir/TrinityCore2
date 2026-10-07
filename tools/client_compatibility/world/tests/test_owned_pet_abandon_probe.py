"""Raw Abandon capture is confined to the disposable owned Wolf6."""
import hashlib,json,struct
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


def tamed_config(tmp_path):
    from tools.client_compatibility.world.tests.test_tamed_disposable_abandon import data
    source,_,_=data();source['model']=None;source['capture_checks']={str(k):v for k,v in source['capture_checks'].items()}
    path=tmp_path/'evidence/tame01/episode.json';path.parent.mkdir(parents=True)
    path.write_text(json.dumps(source));c=config();c.update(schema='client442_owned_pet_abandon_probe_v2',
        pet_number=8,created_at=110,expires_at=190,tame_source={'path':'evidence/tame01/episode.json',
            'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    return c,path


def test_private_probe_binds_later_disposable_number_to_hashed_successful_tame(codec,tmp_path):
    c,_=tamed_config(tmp_path)
    assert probe(codec,tmp_path,c,now=120)
    assert probe(codec,tmp_path,c,struct.pack('<Q',PET),'to_native',now=120)


@pytest.mark.parametrize('fault',['wrong_hash','foreign_number','named_number','named_entry','failed_tame',
    'failed_check','missing_check','armed_source','model_source','late_source','outside_source','symlink',
    'missing_source','unbound_native_number','wrong_owner','source_bool','new_creation_spell'])
def test_private_probe_refuses_unbound_or_failed_tame_source(codec,tmp_path,fault):
    c,path=tamed_config(tmp_path);source=json.loads(path.read_text())
    if fault=='wrong_hash':c['tame_source']['sha256']='0'*64
    elif fault=='foreign_number':c['pet_number']=9
    elif fault=='named_number':c['pet_number']=4
    elif fault=='named_entry':source['retained_pet_after'][1]['entry']=42717
    elif fault=='failed_tame':source['completed']=False
    elif fault=='failed_check':source['capture_checks']['0']=False
    elif fault=='missing_check':source['capture_checks'].pop('0')
    elif fault=='armed_source':source['capture_disarmed']=False
    elif fault=='model_source':source['model']='retired'
    elif fault=='late_source':source['finished_at']=111
    elif fault=='outside_source':c['tame_source']['path']='elsewhere/episode.json'
    elif fault=='symlink':
        target=path.with_name('actual.json');path.rename(target);path.symlink_to(target)
    elif fault=='missing_source':path.unlink()
    elif fault=='unbound_native_number':source['native_pet_after']['fields']['69']=9
    elif fault=='wrong_owner':source['actor']['guid']=7
    elif fault=='source_bool':source['input_sent']='true'
    else:source['retained_pet_after'][1]['CreatedBySpell']=883
    if fault not in ('wrong_hash','symlink','missing_source'):
        path.write_text(json.dumps(source));c['tame_source']['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    assert not probe(codec,tmp_path,c,now=120)
