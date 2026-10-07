"""Native channel writer contracts follow the actual UI153 single Tame cast.

The request/GO are captured bytes from hunter_tame_cast01/episode.json,
SHA256 7fe4bf794e76e3ddfc451173f53969dc40487076bf14c3e1ddfb41f0861a17b8.
Channel bodies here are writer-contract fixtures, not captured UI153 payloads.
"""
from copy import deepcopy
import json,struct,time
import pytest
from tools.client_compatibility.world.buffer import Reader,Writer,player_high
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result,action
from tools.client_compatibility.world.tests.test_hunter_stable_protocol import OWNER,SNAPSHOT

REQUEST=bytes.fromhex('01870cc27a01bc0000000000000000eb05000020a3030000000000000000000000000000000000000000000000000000000000200003a34e20c04a04200000')
GO=bytes.fromhex('0106010601eb0500000009000000000000e730f200024e2000002b0130f106000000000000000002000000f34e202b0130f164000000')
TARGET={'guid':(0xf13<<52)|(299<<32)|0x204e,'map':0,'kind':3}
VISUAL=238368


def start(caster=6,spell=1515,duration=10000,optional=b'\0\0'):
    return bytes((1,caster))+struct.pack('<iI',spell,duration)+optional


def update(caster=6,duration=0):return bytes((1,caster))+struct.pack('<I',duration)


def channel(body=None,name='MSG_CHANNEL_START'):
    return action('tame_channel_response',name,start() if body is None else body)


def cast():return action('cast_request','CMSG_CAST_SPELL',REQUEST)


def go(body=GO):return action('cast_response','SMSG_SPELL_GO',body)


def owned(codec,actions,character=OWNER,snapshot=SNAPSHOT):
    return result(codec,op='stateful',character=character,snapshot=snapshot,units=[TARGET],gameobjects=[],actions=actions)


def decode(packet):
    r=Reader(bytes.fromhex(packet[1]));assert r.guid()==(6,player_high())
    if packet[0]=='SMSG_SPELL_CHANNEL_START':
        assert r.unpack('iII')==(1515,VISUAL,10000) and r.bits(1)==r.bits(1)==0
    else:assert packet[0]=='SMSG_SPELL_CHANNEL_UPDATE' and r.unpack('I')==(0,)
    r.end()


def test_captured_native_go_arms_pinned_modern_channel_and_final_update(codec):
    rows=owned(codec,[cast(),go(),channel(),channel(update(),'MSG_CHANNEL_UPDATE')])
    assert rows[0]==['CMSG_CAST_SPELL','01eb050000000000000002000000f34e202b0130f1']
    assert rows[1][0]=='SMSG_SPELL_GO'
    decode(rows[2]);decode(rows[3])


def test_channel_requires_actual_native_go_and_start_before_update(codec):
    rows=owned(codec,[channel(),cast(),channel(),go(),channel(update(),'MSG_CHANNEL_UPDATE'),channel()])
    assert rows[0] is rows[2] is rows[4] is None;decode(rows[5])


@pytest.mark.parametrize('fault',['foreign','warlock','not_created'])
def test_other_owner_class_or_uncreated_client_receives_no_tame_channel(codec,fault):
    owner=deepcopy(OWNER);snapshot=SNAPSHOT
    if fault=='foreign':owner['guid']=7
    elif fault=='warlock':owner['class']=9
    else:snapshot=None
    assert owned(codec,[cast(),go(),channel()],owner,snapshot)[-1] is None


@pytest.mark.parametrize('body',[start(caster=7),start(spell=883)])
def test_foreign_channel_does_not_consume_valid_pending_tame(codec,body):
    rows=owned(codec,[cast(),go(),channel(body),channel()]);assert rows[2] is None;decode(rows[3])


@pytest.mark.parametrize('body',[b'',start()[:-1],start()+b'x',start(duration=0),
    start(duration=60001),start(optional=b'\1\0'),start(optional=b'\0\1')])
def test_bad_start_remains_rejected_without_destroying_pending_cast(codec,body):
    rows=owned(codec,[cast(),go(),channel(body),channel()]);assert 'error' in rows[2];decode(rows[3])


@pytest.mark.parametrize('body',[b'',update()[:-1],update()+b'x',update(duration=60001)])
def test_bad_update_does_not_consume_actual_completion(codec,body):
    rows=owned(codec,[cast(),go(),channel(),channel(body,'MSG_CHANNEL_UPDATE'),channel(update(),'MSG_CHANNEL_UPDATE')])
    assert 'error' in rows[3];decode(rows[4])


def test_duplicate_start_and_late_updates_are_not_forged(codec):
    rows=owned(codec,[cast(),go(),channel(),channel(),channel(update(),'MSG_CHANNEL_UPDATE'),
        channel(update(),'MSG_CHANNEL_UPDATE'),channel()])
    assert 'error' in rows[3];decode(rows[4]);assert rows[5] is rows[6] is None


def test_new_local_request_does_not_steal_active_channel_completion(codec):
    rows=owned(codec,[cast(),go(),channel(),cast(),channel(update(),'MSG_CHANNEL_UPDATE')])
    decode(rows[4])


def test_malformed_go_cannot_arm_channel_and_logout_revokes_it(codec):
    rows=owned(codec,[cast(),go(GO+b'x'),channel(),go(),channel(),
        action('logout_complete','',b''),channel(update(),'MSG_CHANNEL_UPDATE')])
    assert 'error' in rows[1] and rows[2] is rows[-1] is None;decode(rows[4])


def config():return {'schema':'client442_owned_tame_request_probe_v1','owner':6,'session':'fixture',
    'created_at':100,'expires_at':120}


def probe(codec,tmp_path,c,body=None,direction='from_native',name='MSG_CHANNEL_START',session='fixture',now=110):
    (tmp_path/'run').mkdir(exist_ok=True)
    (tmp_path/'run/owned_tame_request_probe.json').write_text(json.dumps(c))
    return result(codec,op='owned_tame_probe',root=str(tmp_path),direction=direction,name=name,
        session=session,now=now,body=(start() if body is None else body).hex())


def pet_added(level=1,slot=0,flags=1,entry=299,number=6,name='Wolf'):
    return Writer().pack('iiBii',level,slot,flags,entry,number).bits(len(name),8).raw(name.encode()).finish()


def test_private_probe_accepts_exact_native_and_delivered_owned_contracts(codec,tmp_path):
    assert probe(codec,tmp_path,config())
    assert probe(codec,tmp_path,config(),update(),name='MSG_CHANNEL_UPDATE')
    assert probe(codec,tmp_path,config(),pet_added(),name='SMSG_PET_ADDED')
    packets=owned(codec,[cast(),go(),channel(),channel(update(),'MSG_CHANNEL_UPDATE')])[2:]
    for name,body in packets:
        assert probe(codec,tmp_path,config(),bytes.fromhex(body),direction='to_client',name=name)


@pytest.mark.parametrize('key,value',[('schema','other'),('owner',5),('session','foreign'),
    ('created_at',111),('expires_at',110),('expires_at',221)])
def test_foreign_expired_or_unbounded_probe_never_captures(codec,tmp_path,key,value):
    c=config();c[key]=value;assert not probe(codec,tmp_path,c)


@pytest.mark.parametrize('body',[b'',start()[:-1],start()+b'x',start(caster=7),start(spell=883),
    start(duration=0),start(duration=60001),start(optional=b'\1\0'),start(optional=b'\0\1')])
def test_private_probe_excludes_foreign_or_incomplete_channels(codec,tmp_path,body):
    assert not probe(codec,tmp_path,config(),body)


@pytest.mark.parametrize('change',[{'level':10},{'slot':5},{'flags':3},{'entry':42717},
    {'number':4},{'name':'Harnesswolf'}])
def test_private_probe_excludes_unrelated_pet_catalogs(codec,tmp_path,change):
    assert not probe(codec,tmp_path,config(),pet_added(**change),name='SMSG_PET_ADDED')


def test_private_probe_excludes_auth_and_never_expands_global_packet_bodies(codec,tmp_path):
    assert not probe(codec,tmp_path,config(),session='other')
    assert not probe(codec,tmp_path,config(),direction='from_client')
    assert not probe(codec,tmp_path,config(),name='SMSG_AUTH_RESPONSE')
    c=config();c.update(created_at=time.time()-1,expires_at=time.time()+60)
    assert probe(codec,tmp_path,c,now=time.time())
    (tmp_path/'evidence').mkdir();(tmp_path/'logs').mkdir()
    result(codec,op='packet_diagnostic',root=str(tmp_path),name='MSG_CHANNEL_START',body=start().hex(),direction='from_native')
    rows=[json.loads(line) for line in (tmp_path/'evidence/owned_tame_request_packets.jsonl').read_text().splitlines()]
    assert len(rows)==1 and rows[0]['name']=='MSG_CHANNEL_START' and rows[0]['body']==start().hex()
    assert not (tmp_path/'evidence/world_packets.jsonl').exists()
