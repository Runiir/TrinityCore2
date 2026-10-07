"""Pinned StableInfo masks preserve the native owned catalog and model identity."""
from copy import deepcopy
import struct
import pytest
from tools.client_compatibility.world.buffer import Reader,Writer,player_high
from tools.client_compatibility.world.gameobjects import modern_guid
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result,action

MASTER=(0xf13<<52)|(6749<<32)|202103
OWNER={'guid':6,'map':0,'class':3,'name':'Harnesshunt'}
SNAPSHOT={'guid':6,'map':0,'kind':4,'fields':{INDEX['UNIT_FIELD_BYTES_0']:1|(3<<8)}}
UNIT={'guid':MASTER,'map':0,'kind':3,'fields':{INDEX['UNIT_NPC_FLAGS']:4194304}}
MODEL={'id':4,'owner':6,'entry':42717,'modelid':2404,'PetType':1}


def catalog(guid=MASTER,slot=0,number=4,entry=42717,level=10,name='Harnesswolf',flags=None,last=20):
    flags=(3 if slot>4 else 1) if flags is None else flags
    return (Writer().pack('QBBiIII',guid,1,last,slot,number,entry,level)
        .raw(name.encode()+b'\0').pack('B',flags).finish())


def read(body=None):return action('stable_request','CMSG_REQUEST_STABLED_PETS',
    Writer().guid(*modern_guid(MASTER,0)).finish() if body is None else body)


def reply(body=None,models=None):return {**action('stable_response','MSG_LIST_STABLED_PETS',
    catalog() if body is None else body),'models':[MODEL] if models is None else models}


def owned(codec,actions,unit=UNIT,snapshot=SNAPSHOT,character=OWNER):
    return result(codec,op='stateful',character=character,snapshot=snapshot,gameobjects=[],
        units=[] if unit is None else [unit],actions=actions)


def decode_update(packet):
    assert packet[0]=='SMSG_UPDATE_OBJECT';r=Reader(bytes.fromhex(packet[1]))
    assert r.unpack('HI')==(0,1) and r.bits(1)==1 and r.bits(1)==0
    length,=r.unpack('I');outer=Reader(r.raw(length));r.end()
    assert outer.unpack('B')==(0,) and outer.guid()==(6,player_high())
    length,=outer.unpack('I');f=Reader(outer.raw(length));outer.end()
    assert f.unpack('BBBI')==(1,0,3,128)
    assert f.unpack('I')==(24,) and f.bits(14)==0 and f.bits(32)==64 and f.bits(32)==6
    assert f.unpack('B')==(16,) and f.bits(1)==1 and f.bits(3)==7
    count=f.bits(32);assert f.bits(count)==(1<<count)-1;f.align();pets=[]
    for _ in range(count):
        assert f.bits(9)==511;f.align()
        values=f.unpack('5IBB');size=f.bits(8);name=f.raw(size).decode()
        pets.append((*values,name))
    guid=f.guid();f.end();return pets,guid


def test_complete_owned_catalog_has_pinned_masks_model_and_actual_capacity(codec):
    rows=owned(codec,[read(),reply()]);assert rows[0]==['MSG_LIST_STABLED_PETS',struct.pack('<Q',MASTER).hex()]
    assert decode_update(rows[1])==([(0,4,42717,2404,10,1,0,'Harnesswolf')],modern_guid(MASTER,0))
    assert decode_update(owned(codec,[reply(catalog(slot=5))])[0])[0]==[(5,4,42717,2404,10,3,0,'Harnesswolf')]


@pytest.mark.parametrize('fault',['unseen','wrong_map','not_stable','player','warlock','no_owner','not_created'])
def test_reads_require_current_owned_hunter_and_visible_native_master(codec,fault):
    unit=deepcopy(UNIT);snapshot=deepcopy(SNAPSHOT);character=deepcopy(OWNER)
    if fault=='unseen':unit=None
    elif fault=='wrong_map':unit['map']=1
    elif fault=='not_stable':unit['fields'][INDEX['UNIT_NPC_FLAGS']]=1
    elif fault=='player':unit['kind']=4
    elif fault=='warlock':snapshot['fields'][INDEX['UNIT_FIELD_BYTES_0']]=1|(9<<8)
    elif fault=='no_owner':character['guid']=0
    elif fault=='not_created':snapshot=None
    assert 'error' in owned(codec,[read()],unit,snapshot,character)[0]


@pytest.mark.parametrize('body',[b'',Writer().guid(0,0).finish(),
    Writer().guid(*modern_guid(MASTER,1)).finish(),Writer().guid(*modern_guid(MASTER+1,0)).finish(),
    Writer().guid(*modern_guid(MASTER,0)).finish()+b'x'])
def test_foreign_or_incomplete_request_is_not_forwarded(codec,body):
    rows=owned(codec,[read(body),read()]);assert 'error' in rows[0] and rows[1][0]=='MSG_LIST_STABLED_PETS'


@pytest.mark.parametrize('body',[catalog(slot=-1),catalog(slot=21),catalog(number=0),catalog(entry=0),
    catalog(level=0),catalog(level=86),catalog(name=''),catalog(name='x'*256),catalog(flags=3),
    catalog(last=21),catalog()[:-1],catalog()+b'x'])
def test_bad_native_catalog_cannot_replace_valid_owned_state(codec,body):
    rows=owned(codec,[reply(),reply(body),reply()]);assert 'error' in rows[1]
    assert rows[0]==rows[2]


@pytest.mark.parametrize('fault',['missing','foreign_owner','wrong_entry','zero_model','wrong_type','duplicate'])
def test_models_bind_fresh_native_owner_number_entry_without_guessing(codec,fault):
    row=deepcopy(MODEL);models=[row]
    if fault=='missing':models=[]
    elif fault=='duplicate':models=[row,row]
    else:row[{'foreign_owner':'owner','wrong_entry':'entry','zero_model':'modelid','wrong_type':'PetType'}[fault]]=0
    assert 'error' in owned(codec,[reply(models=models)])[0]


def test_zero_master_catalog_never_forges_an_npc_open_and_logout_revokes_reads(codec):
    pets,guid=decode_update(owned(codec,[reply(catalog(guid=0))])[0]);assert guid==(0,0) and len(pets)==1
    rows=owned(codec,[reply(),action('logout_complete','',b''),read()]);assert 'error' in rows[-1]


def test_expiring_private_probe_can_capture_exact_native_catalog_only(codec,tmp_path):
    from tools.client_compatibility.world.tests.test_owned_stable_request_probe import config,probe
    c=config();c.update(native_master_guid=MASTER,modern_master_guid=list(modern_guid(MASTER,0)))
    assert probe(codec,tmp_path,c,catalog(),direction='from_native',name='MSG_LIST_STABLED_PETS')
    assert not probe(codec,tmp_path,c,catalog(guid=MASTER+1),direction='from_native',name='MSG_LIST_STABLED_PETS')
    assert not probe(codec,tmp_path,c,catalog(),direction='from_native',name='SMSG_AUTH_RESPONSE')
    assert not probe(codec,tmp_path,c,catalog()+b'x',direction='from_native',name='MSG_LIST_STABLED_PETS')


def test_glyph_group_preserves_present_stable_without_emitting_a_new_catalog(codec):
    fields={INDEX['PLAYER_GLYPHS_ENABLED']:511}
    snapshot={'guid':6,'fields':fields,'pet_stable':{'Pets':[],'StableMaster':[0,0]}}
    body=result(codec,op='glyph_update',snapshot=snapshot,changed=fields)
    r=Reader(bytes.fromhex(body));assert r.unpack('B')==(0,) and r.guid()==(6,player_high())
    length,=r.unpack('I');f=Reader(r.raw(length));r.end()
    assert f.unpack('BBBI')==(1,0,3,128) and f.unpack('I')==(8,)
    assert f.bits(14)==0 and f.bits(32)==((1<<6)|(1<<31))
    assert f.unpack('H')==(511,) and f.bits(1)==1;f.end()


def test_native_catalog_opens_stock_interaction_once_and_close_allows_normal_reopen(codec):
    notify=action('stable_open_response','',b'')
    close=action('bank_close','CMSG_CLOSE_INTERACTION',Writer().guid(*modern_guid(MASTER,0)).finish())
    rows=owned(codec,[reply(),notify,reply(),notify,close,reply(),notify])
    expected=['SMSG_NPC_INTERACTION_OPEN_RESULT',Writer().guid(*modern_guid(MASTER,0)).pack('i',22).bits(1,1).finish().hex()]
    assert rows[1]==expected and rows[3] is None and rows[6]==expected
    assert owned(codec,[reply(catalog(guid=0)),notify])[1] is None


def gossip(guid=MASTER):
    body=Writer().pack('QIIIiBBI',guid,9821,13557,1,0,12,0,0).raw(b'Stable here\0\0').pack('I',0).finish()
    return action('gossip_response','SMSG_GOSSIP_MESSAGE',body)


@pytest.mark.parametrize('lookup_pending',[False,True])
def test_native_stable_transition_does_not_close_new_stock_interaction(codec,lookup_pending):
    started=action('stable_catalog_started','MSG_LIST_STABLED_PETS',catalog()) if lookup_pending else reply()
    complete=action('gossip_response','SMSG_GOSSIP_COMPLETE',b'')
    rows=owned(codec,[gossip(),started,complete,complete])
    assert rows[2] is None and rows[3]==['SMSG_GOSSIP_COMPLETE','00']


def test_normal_gossip_choice_reopens_and_zero_master_does_not_suppress_gossip_close(codec):
    notify=action('stable_open_response','',b'')
    request=Writer().guid(*modern_guid(MASTER,0)).pack('Ii',9821,0).bits(0,8).finish()
    rows=owned(codec,[gossip(),reply(),notify,action('gossip_request','CMSG_GOSSIP_SELECT_OPTION',request),reply(),notify])
    assert rows[5]==rows[2] and rows[5][0]=='SMSG_NPC_INTERACTION_OPEN_RESULT'
    rows=owned(codec,[gossip(),reply(catalog(guid=0)),action('gossip_response','SMSG_GOSSIP_COMPLETE',b'')])
    assert rows[2]==['SMSG_GOSSIP_COMPLETE','00']
