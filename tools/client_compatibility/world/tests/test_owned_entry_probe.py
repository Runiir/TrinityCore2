"""Capture only the two observed lobby requests under an exact closed entry lease."""
import hashlib,json,time
import pytest
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result


def source():
    return {'completed':True,'failure':None,'phase':'owned_class_entered','model':None,'finished_at':99,
        'checks':{str(i):True for i in range(9)},'native_session':'fixture','runtime':{'client':3,'modern_world':2,'worldserver':1},
        'actor':{'guid':6,'account_id':2,'class':3,'level':10}}


def config(tmp_path):
    path=tmp_path/'evidence/entry/episode.json';path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(source()))
    return {'schema':'client442_owned_entry_request_probe_v1','owner':6,'account_id':2,'session':'fixture',
        'created_at':100,'expires_at':220,'runtime':source()['runtime'],
        'entry_source':{'path':'evidence/entry/episode.json','sha256':hashlib.sha256(path.read_bytes()).hexdigest()}}


def probe(codec,tmp_path,c,**kwargs):
    (tmp_path/'run').mkdir(exist_ok=True)
    (tmp_path/'run/owned_entry_request_probe.json').write_text(json.dumps(c))
    return result(codec,op='owned_entry_probe',root=str(tmp_path),**{
        'direction':'from_client','name':'CMSG_GET_ACCOUNT_CHARACTER_LIST','body':'0000000000',
        'session':'fixture','now':110,**kwargs})


@pytest.mark.parametrize('name',['CMSG_GET_ACCOUNT_CHARACTER_LIST','CMSG_LOADING_SCREEN_NOTIFY'])
def test_only_the_two_observed_five_byte_requests_are_admitted(codec,tmp_path,name):
    assert probe(codec,tmp_path,config(tmp_path),name=name)


@pytest.mark.parametrize('fault',['schema','owner','account','session','created','expired','duration','runtime',
    'hash','outside','missing','symlink','failed','phase','model','source_session','source_actor',
    'source_runtime','missing_check','failed_check','string_check','late_source'])
def test_unbound_or_failed_sources_cannot_arm_a_lobby_capture(codec,tmp_path,fault):
    c=config(tmp_path);p=tmp_path/c['entry_source']['path'];s=source()
    if fault=='schema':c['schema']='other'
    elif fault=='owner':c['owner']=5
    elif fault=='account':c['account_id']=1
    elif fault=='session':c['session']='foreign'
    elif fault=='created':c['created_at']=111
    elif fault=='expired':c['expires_at']=110
    elif fault=='duration':c['expires_at']=221
    elif fault=='runtime':c['runtime']['client']=99
    elif fault=='hash':c['entry_source']['sha256']='0'*64
    elif fault=='outside':c['entry_source']['path']='../episode.json'
    elif fault=='missing':p.unlink()
    elif fault=='symlink':
        real=p.with_name('original.json');p.rename(real);p.symlink_to(real)
    elif fault=='failed':s['completed']=False
    elif fault=='phase':s['phase']='loading_failed'
    elif fault=='model':s['model']='retired'
    elif fault=='source_session':s['native_session']='foreign'
    elif fault=='source_actor':s['actor']['guid']=1
    elif fault=='source_runtime':s['runtime']['client']=99
    elif fault=='missing_check':s['checks'].pop('0')
    elif fault=='failed_check':s['checks']['0']=False
    elif fault=='string_check':s['checks']['0']='true'
    else:s['finished_at']=100
    if fault in ('failed','phase','model','source_session','source_actor','source_runtime',
            'missing_check','failed_check','string_check','late_source'):
        p.write_text(json.dumps(s));c['entry_source']['sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
    assert not probe(codec,tmp_path,c)


@pytest.mark.parametrize('change',[{'name':'CMSG_AUTH_SESSION'},{'name':'CMSG_AUTH_CONTINUED_SESSION'},
    {'name':'SMSG_CONNECT_TO'},{'name':'CMSG_CAST_SPELL'},{'direction':'to_native'},
    {'direction':'from_native'},{'session':'foreign'},{'body':''},{'body':'00000000'},
    {'body':'000000000000'},{'now':99},{'now':220}])
def test_secrets_other_actions_foreign_sessions_and_wrong_widths_are_excluded(codec,tmp_path,change):
    assert not probe(codec,tmp_path,config(tmp_path),**change)


def test_raw_event_is_separate_and_authentication_remains_excluded(codec,tmp_path):
    c=config(tmp_path);now=time.time();c.update(created_at=now-1,expires_at=now+100)
    assert probe(codec,tmp_path,c,now=now)
    result(codec,op='packet_diagnostic',root=str(tmp_path),name='CMSG_GET_ACCOUNT_CHARACTER_LIST',body='0000000000')
    rows=[json.loads(line) for line in (tmp_path/'evidence/owned_entry_request_packets.jsonl').read_text().splitlines()]
    assert len(rows)==1 and rows[0]['name']=='CMSG_GET_ACCOUNT_CHARACTER_LIST'
    result(codec,op='packet_diagnostic',root=str(tmp_path),name='CMSG_AUTH_SESSION',body='0000000000')
    assert len((tmp_path/'evidence/owned_entry_request_packets.jsonl').read_text().splitlines())==1
