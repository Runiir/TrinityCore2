"""Differential wire checks for the standalone C++ migration.

Set CLIENT442_CODEC to the separately built binary. Python remains only the
test oracle; the candidate executable does not import or embed Python.
"""
import hashlib
import json
import os
from pathlib import Path
import random
import struct
import subprocess

from Crypto.Cipher import AES
import pytest

from tools.client_compatibility.world import crypto,fields
from tools.client_compatibility.world.buffer import Writer


@pytest.fixture(scope='module')
def codec():
    path=os.environ.get('CLIENT442_CODEC')
    if not path:pytest.skip('build the standalone bridge and set CLIENT442_CODEC')
    process=subprocess.Popen([path,str(Path(fields.__file__).parent)],stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    def call(**request):
        process.stdin.write(json.dumps(request)+'\n');process.stdin.flush()
        line=process.stdout.readline()
        if not line:raise AssertionError(process.stderr.read())
        return json.loads(line)
    yield call
    try:process.stdin.close()
    except BrokenPipeError:pass
    process.wait(timeout=5)
    assert process.returncode==0,process.stderr.read()


def result(codec,**request):
    answer=codec(**request)
    assert 'error' not in answer,answer
    return answer['result']


def test_native_crypto_matches_both_build_variants(codec):
    material=bytes(range(64));local=bytes(range(32));server=local[::-1]
    for variant in crypto.BUILD_KEYS:
        proof=crypto.mac(hashlib.sha512(material+crypto.BUILD_KEYS[variant]).digest(),
            local+server+crypto.AUTH_SEED)[:24]
        expected=crypto.derive(material,local,server,proof,variant)
        actual=result(codec,op='derive',material=material.hex(),local=local.hex(),server=server.hex(),
            proof=proof.hex(),variant=variant)
        assert actual==[v.hex() for v in expected]
        assert 'error' in codec(op='derive',material=material.hex(),local=local.hex(),
            server=server.hex(),proof=bytes(24).hex(),variant=variant)


def test_native_ed25519_context_signature(codec):
    for key in [bytes(32),bytes(range(32))]:
        assert result(codec,op='signature',key=key.hex())==crypto.enabled_signature(key).hex()


def test_native_aes_counter_direction_and_integrity(codec):
    key=bytes(range(32))
    for counter in [0,1,254,2**32+7]:
        for body in [b'',b'packet',bytes(range(256))*8,bytes(range(256))*512]:
            oracle=crypto.PacketCrypt();oracle.key=key;oracle.send_counter=counter
            assert result(codec,op='encode',key=key.hex(),counter=counter,opcode=123,body=body.hex())==oracle.encode(123,body).hex()
            cipher=AES.new(key,AES.MODE_GCM,nonce=struct.pack('<QI',counter,0x544e4c43),mac_len=12)
            payload,tag=cipher.encrypt_and_digest(struct.pack('<I',123)+body)
            args=dict(op='decode',key=key.hex(),counter=counter,payload=payload.hex(),tag=tag.hex())
            if len(body)>65532:
                assert 'error' in codec(**args)  # Incoming client frames retain their smaller bound.
                continue
            assert result(codec,**args)==[123,body.hex()]
            assert 'error' in codec(**{**args,'counter':counter+1})
            assert 'error' in codec(**{**args,'tag':(bytes([tag[0]^1])+tag[1:]).hex()})
    assert result(codec,op='encode',key='',counter=0,opcode=123,body='')==crypto.PacketCrypt().encode(123,b'').hex()
    assert 'error' in codec(op='decode',key='',counter=0,payload='7b000000',tag='01'*12)


def test_native_legacy_header_cipher(codec):
    key=bytes(range(40));payload=bytes(range(256))*8
    for seed in ['c2b3723cc6aed9b5343c53ee2f4367ce','cc98ae04e897eaca12ddc09342915357']:
        assert result(codec,op='legacy',key=key.hex(),seed=seed,body=payload.hex())==crypto.legacy_crypt(key,bytes.fromhex(seed)).encrypt(payload).hex()


def test_native_guids_preserve_high_bits(codec):
    rng=random.Random(60895)
    for low,high in [(0,0),(1,2<<58),(2**64-1,2**64-1)]+[(rng.getrandbits(64),rng.getrandbits(64)) for _ in range(40)]:
        assert result(codec,op='guid',value=[low,high])==Writer().guid(low,high).finish().hex()


def test_native_packing_rejects_width_overflow_instead_of_truncating(codec):
    for fmt,width,signed in [('B',8,False),('b',8,True),('H',16,False),('h',16,True),
        ('I',32,False),('i',32,True),('Q',64,False),('q',64,True)]:
        lower=-(2**(width-1)) if signed else 0
        upper=2**(width-int(signed))-1
        for value in [lower,upper]:
            assert result(codec,op='pack',format=fmt,values=[value])==struct.pack('<'+fmt,value).hex()
        for value in [lower-1,upper+1,1.5]:
            assert 'error' in codec(op='pack',format=fmt,values=[value])


def test_native_create_serializers_match_supported_roots(codec):
    cases={
        'ObjectData':{'EntryID':206835,'Scale':1.0},
        'UnitData':{'Health':70000,'MaxHealth':120000,'Flags':4,'MountDisplayID':16085,
            'Power':[0,100,0,0,0],'MaxPower':[0,100,0,0,0],'Race':1,'ClassId':1,'Level':85},
        'PlayerData':{'Name':'Harnessone','VisibleItems':[{'ItemID':65266}]*19},
        'ActivePlayerData':{'ResearchSites':[[351,363]],'Research':[[{'ResearchProjectID':101}]],
            'InvSlots':[[0,0]]*146,'Skill':{'SkillLineID':[794],'SkillRank':[525],'SkillMaxRank':[525]}},
        'GameObjectData':{'DisplayID':1,'CreatedBy':[1,2<<58],'ParentRotation':{'x':0,'y':0,'z':0,'w':1},'TypeID':5},
        'ItemData':{'Owner':[1,2<<58],'ItemBonusKey':{'ItemID':65266},'SpellCharges':[-1,0,0,0,0]},
        'ContainerData':{'NumSlots':16,'Slots':[[0,0]]*36},
    }
    for kind,values in cases.items():
        for visibility in [0,1]:
            expected=Writer();fields.serialize(expected,kind,values,visibility)
            assert result(codec,op='fields',kind=kind,values=values,visibility=visibility)==expected.finish().hex(),(kind,visibility)


def test_native_owned_movement_matches_every_supported_opcode(codec):
    from tools.client_compatibility.world import movement
    from tools.client_compatibility.world.tests.test_world_protocol import move_body
    for body in [move_body(),move_body(guid=7,x=100)]:
        guid=1 if body==move_body() else 7
        state=movement.parse(body,guid)
        for name in sorted(movement.SUPPORTED):
            expected=movement.encode(name,guid,state)
            assert result(codec,op='movement',body=body.hex(),guid=guid,name=name)==[expected[0],expected[1].hex()]
    for body in [move_body(2),move_body(x=18000),move_body()[:-1],move_body()+b'\x00']:
        assert 'error' in codec(op='movement',body=body.hex(),guid=1,name='CMSG_MOVE_STOP')


def test_native_objects_preserve_fields_inventory_professions_and_visible_objects(codec):
    from tools.client_compatibility.world import objects,inventory,gameobjects,units
    native={objects.INDEX['UNIT_FIELD_HEALTH']:70000,objects.INDEX['UNIT_FIELD_MAXHEALTH']:120000,
        objects.INDEX['UNIT_FIELD_BYTES_0']:1|1<<8,objects.INDEX['UNIT_FIELD_LEVEL']:85,
        objects.INDEX['PLAYER_PROFESSION_SKILL_LINE_1']:794,objects.INDEX['PLAYER_FIELD_RESEARCH_SITE_1']:351|363<<16,
        objects.INDEX['PLAYER_FIELD_RESEARCH_PROJECT_1']:101,objects.INDEX['OBJECT_FIELD_SCALE_X']:struct.unpack('<I',struct.pack('<f',1))[0]}
    snapshot={'guid':1,'kind':4,'map':530,'fields':native,'movement':{'position':[1,2,3,4],
        'flags':0,'flags2':0,'time':42,'pitch':0,'speeds':[2.5,7,4.5,4.72,2.5,7,4.5,3.14,3.14]}}
    character={'guid':1,'name':'Harnessone','gender':0}
    assert result(codec,op='object_values',snapshot=snapshot,character=character)==json.loads(json.dumps(objects.field_values(snapshot,character)))
    assert result(codec,op='object_block',kind='player',snapshot=snapshot,character=character)==objects.player_block(snapshot,character).hex()
    item={**snapshot,'guid':0x4000000000000007,'kind':2,'fields':{
        objects.INDEX['OBJECT_FIELD_SCALE_X']:native[objects.INDEX['OBJECT_FIELD_SCALE_X']],
        objects.INDEX['ITEM_FIELD_OWNER']:1,objects.INDEX['CONTAINER_FIELD_NUM_SLOTS']:16}}
    assert result(codec,op='object_block',kind='item',snapshot=item,character=character)==inventory.item_block(item).hex()
    go={**snapshot,'guid':(0xf11<<52)|(206835<<32)|19,'kind':5}
    assert result(codec,op='object_block',kind='gameobject',snapshot=go,character=character)==gameobjects.block(go).hex()
    unit={**snapshot,'guid':(0xf13<<52)|(1234<<32)|28,'kind':3}
    assert result(codec,op='object_block',kind='unit',snapshot=unit,character=character)==units.block(unit,character).hex()


def stateful(codec,character,actions,gameobjects=(),units=(),snapshot=None,paths=()):
    return result(codec,op='stateful',character=character,actions=actions,
        gameobjects=list(gameobjects),units=list(units),snapshot=snapshot,paths=list(paths))


def action(fn,name,body):
    return dict(fn=fn,name=name,body=body.hex())


def packet(reply):
    return None if reply is None else [reply[0],reply[1].hex()]


def test_native_survey_start_ack_cast_bar_cancel_and_failure_match(codec):
    from types import SimpleNamespace
    from tools.client_compatibility.world import casting
    character=dict(guid=1,map=0);owner=SimpleNamespace(character=character)
    request=bytes.fromhex('018702c2904ebc0000000000000000433a010067f1050000000000000000000000000000000000000000000000000000000000000000000000')
    start=bytes.fromhex('0101010101433a01000208000000000000e80300004000000000ab9c23c6aa0ae1c38874394200000000')
    encoded,_=casting.request(owner,request)
    prepare=casting.prepare(owner,start)
    response=casting.response(owner,'SMSG_SPELL_START',start)
    cancel=Writer().guid(*owner.casts[1]['server_guid']).pack('I',80451).finish()
    failure=struct.pack('<BiB',1,80451,99)
    actions=[action('cast_request','CMSG_CAST_SPELL',request),action('cast_prepare','SMSG_SPELL_START',start),
        action('cast_response','SMSG_SPELL_START',start),action('cast_cancel','CMSG_CANCEL_CAST',cancel),
        action('cast_response','SMSG_CAST_FAILED',failure)]
    assert stateful(codec,character,actions)==[
        ['CMSG_CAST_SPELL',encoded.hex()],['SMSG_SPELL_PREPARE',prepare.hex()],['SMSG_SPELL_START',response.hex()],
        ['CMSG_CANCEL_CAST',casting.cancel(owner,cancel).hex()],['SMSG_CAST_FAILED',casting.response(owner,'SMSG_CAST_FAILED',failure).hex()]]


def test_native_artifact_gather_loot_and_duplicate_guards_match(codec):
    from types import SimpleNamespace
    from tools.client_compatibility.world import casting,looting
    native=(0xf11<<52)|(203071<<32)|1559;record=dict(guid=native,map=0)
    character=dict(guid=1,map=0);owner=SimpleNamespace(character=character,visible_gameobjects={native:record})
    gather=bytes.fromhex('018707c23e48bc0000000000000000fb20010035e3050000000000000000000000000000000000000000000000000000000080000003a71706c04fc6042c0000')
    encoded,_=casting.request(owner,gather)
    loot=struct.pack('<QBIBBBII',native,1,0,0,1,0,384,5)
    reply=looting.response(owner,'SMSG_LOOT_RESPONSE',loot)
    item=Writer().pack('I',1).guid(*owner.loot['guid']).pack('B',0).bits(0,1).finish()
    duplicate=Writer().pack('I',2).guid(*owner.loot['guid']).pack('B',0).guid(*owner.loot['guid']).pack('B',0).bits(0,1).finish()
    results=stateful(codec,character,[action('cast_request','CMSG_CAST_SPELL',gather),
        action('loot_response','SMSG_LOOT_RESPONSE',loot),action('loot_request','CMSG_LOOT_ITEM',item),
        action('loot_request','CMSG_LOOT_ITEM',duplicate)],gameobjects=[record])
    assert results[:3]==[['CMSG_CAST_SPELL',encoded.hex()],packet(reply),['CMSG_LOOT_CURRENCY','00']]
    assert 'error' in results[3]
    assert 'error' in stateful(codec,character,[action('cast_request','CMSG_CAST_SPELL',gather)])[0]


def test_native_mount_aura_speed_ack_replay_and_fields_match(codec):
    from types import SimpleNamespace
    from tools.client_compatibility.world import casting,auras,movement_controls,player_updates
    from tools.client_compatibility.world.tests.test_mounts import status
    character=dict(guid=1,map=0,name='Harnessone',gender=0);owner=SimpleNamespace(character=character,self_snapshot={'fields':{}})
    aura=casting.packed(Writer(),1).pack('BiHBB',0,32235,0x19,85,0).finish()
    cancel=Writer().pack('I',32235).guid(1,2<<58|1<<42).finish()
    speed=bytes.fromhex('04010000000000604100')
    ack=status()+struct.pack('<If',1,14)
    fields=bytes.fromhex('0000010000000001010300000000000020a0002200000800000831000000214500000000000000000000')
    expected=[packet(auras.response(owner,'SMSG_AURA_UPDATE',aura)),['CMSG_CANCEL_AURA',auras.cancel(owner,cancel).hex()],
        ['SMSG_MOVE_SET_RUN_SPEED',movement_controls.response(owner,'SMSG_MOVE_SET_RUN_SPEED',speed).hex()],
        packet(movement_controls.acknowledgement(owner,'CMSG_MOVE_FORCE_RUN_SPEED_CHANGE_ACK',ack))]
    values=stateful(codec,character,[action('aura_response','SMSG_AURA_UPDATE',aura),action('aura_cancel','CMSG_CANCEL_AURA',cancel),
        action('movement_control','SMSG_MOVE_SET_RUN_SPEED',speed),action('movement_ack','CMSG_MOVE_FORCE_RUN_SPEED_CHANGE_ACK',ack),
        action('movement_ack','CMSG_MOVE_FORCE_RUN_SPEED_CHANGE_ACK',ack),action('object_updates','SMSG_UPDATE_OBJECT',fields)],snapshot={'fields':{}})
    assert values[:4]==expected
    assert 'error' in values[4]
    assert values[5]==['SMSG_UPDATE_OBJECT',player_updates.updates(owner,fields).hex()]


def test_native_portal_far_transfer_preserves_order_and_rejects_replay(codec):
    from types import SimpleNamespace
    from tools.client_compatibility.world import transfers
    character=dict(guid=1,map=0);snapshot={'movement':{'position':[10,20,30,1]}}
    owner=SimpleNamespace(character=character.copy(),self_snapshot=snapshot)
    inputs=[('transfer_response','SMSG_TRANSFER_PENDING',Writer().bits(0,2).pack('i',530).finish()),
        ('transfer_response','SMSG_SUSPEND_TOKEN',Writer().pack('I',1).bits(1,1).finish()),
        ('transfer_request','CMSG_SUSPEND_TOKEN_RESPONSE',struct.pack('<I',1)),
        ('transfer_response','SMSG_NEW_WORLD',struct.pack('<fffif',100,2,300,530,200)),
        ('transfer_request','CMSG_WORLD_PORT_RESPONSE',b'')]
    expected=[]
    for fn,name,body in inputs:expected.append(packet(getattr(transfers,'response' if fn.endswith('response') else 'request')(owner,name,body)))
    values=stateful(codec,character,[action(*args) for args in inputs]+[action('transfer_request','CMSG_WORLD_PORT_RESPONSE',b'')],snapshot=snapshot)
    assert values[:5]==expected
    assert 'error' in values[5]


def test_native_taxi_multihop_and_gossip_ownership_match(codec,monkeypatch):
    from types import SimpleNamespace
    from tools.client_compatibility.world import taxi,gossip,gameobjects
    guid=(0xf13<<52)|(2409<<32)|123;record=dict(guid=guid,map=0)
    owner=SimpleNamespace(visible_units={guid:record})
    paths=[dict(source=1,destination=2,cost=5),dict(source=2,destination=3,cost=6)]
    monkeypatch.setattr(taxi,'paths',lambda:paths)
    menu=Writer().pack('IQII',1,guid,1,2).raw(bytes([7,0])).finish()
    activate=Writer().guid(*gameobjects.modern_guid(guid,0)).pack('III',3,0,0).finish()
    native=Writer().pack('QIIIiBBI',guid,10,68,1,3,2,0,0).raw(b'Flight route\0\0').pack('I',0).finish()
    select=Writer().guid(*gameobjects.modern_guid(guid,0)).pack('Ii',10,3).bits(0,8).finish()
    bad=Writer().guid(*gameobjects.modern_guid(guid,0)).pack('Ii',10,4).bits(0,8).finish()
    expected=[packet(taxi.response(owner,'SMSG_SHOWTAXINODES',menu)),packet(taxi.request(owner,'CMSG_ACTIVATE_TAXI',activate)),
        packet(gossip.response(owner,'SMSG_GOSSIP_MESSAGE',native)),packet(gossip.request(owner,'CMSG_GOSSIP_SELECT_OPTION',select))]
    values=stateful(codec,dict(guid=1,map=0),[action('taxi_response','SMSG_SHOWTAXINODES',menu),
        action('taxi_request','CMSG_ACTIVATE_TAXI',activate),action('gossip_response','SMSG_GOSSIP_MESSAGE',native),
        action('gossip_request','CMSG_GOSSIP_SELECT_OPTION',select),action('gossip_request','CMSG_GOSSIP_SELECT_OPTION',bad)],units=[record],paths=paths)
    assert values[:4]==expected
    assert 'error' in values[4]


def test_native_capabilities_and_currency_keep_server_values(codec):
    from tools.client_compatibility.world import initialization,currency
    from itertools import product
    spells=Writer().pack('BH',1,3).pack('IhIhIhH',80451,0,32235,0,90265,0,0).finish()
    buttons=Writer().pack('144I',80451,32235,*([0]*142)).pack('B',0).finish()
    cases=[('SMSG_SEND_KNOWN_SPELLS',spells),('SMSG_UPDATE_ACTION_BUTTONS',buttons),
        ('SMSG_SET_PROFICIENCY',struct.pack('<BI',2,0x1234)),('SMSG_SEND_UNLEARN_SPELLS',struct.pack('<II',1,99))]
    expected=[packet((name,initialization.translate(name,body))) for name,body in cases]
    assert stateful(codec,dict(guid=1),[action('initialize',name,body) for name,body in cases])==expected
    cases=[]
    for weekly,tracked,suppress in product(range(2),repeat=3):
        w=Writer().bits(weekly,1).bits(tracked,1).bits(suppress,1)
        if tracked:w.pack('i',100)
        w.pack('ii',154,384)
        if weekly:w.pack('i',5)
        cases.append(('SMSG_SET_CURRENCY',w.finish()))
    setup=Writer().bits(2,23).bits(1,1).bits(3,4).bits(1,1).bits(1,1)
    setup.bits(0,1).bits(0,4).bits(0,1).bits(0,1).pack('6I',154,200,180,384,5,138).pack('I',398).finish()
    cases.append(('SMSG_SETUP_CURRENCY',setup.finish()))
    assert stateful(codec,dict(guid=1),[action('currency',name,body) for name,body in cases])==[
        packet((name,currency.translate(name,body))) for name,body in cases]


@pytest.mark.parametrize('captured',json.loads((Path(__file__).parent/'fixtures/creature_splines.json').read_text()))
def test_native_captured_creature_splines_match(codec,captured):
    from types import SimpleNamespace
    from tools.client_compatibility.world import creature_movement as movement
    body=bytes.fromhex(captured['body']);parsed=movement.parse(body)
    record=dict(guid=parsed['guid'],map=530,movement=dict(position=[0,0,0,0],time=1234))
    owner=SimpleNamespace(visible_units={record['guid']:record})
    expected=[['SMSG_MOVE_UPDATE',movement.position_update(owner,body).hex()],packet(movement.response(owner,'SMSG_ON_MONSTER_MOVE',body))]
    assert stateful(codec,dict(guid=1,map=530),[action('creature_movement','SMSG_ON_MONSTER_MOVE',body)],units=[record])==expected


def test_native_visible_npc_text_query_reply_and_replay_match(codec,monkeypatch):
    from types import SimpleNamespace
    from tools.client_compatibility.world import npc_text,gossip,gameobjects
    guid=(0xf13<<52)|(2409<<32)|123;record=dict(guid=guid,map=0)
    owner=SimpleNamespace(visible_units={guid:record})
    menu=Writer().pack('QIII',guid,10,7778,0).pack('I',0).finish()
    greeting=packet(gossip.response(owner,'SMSG_GOSSIP_MESSAGE',menu))
    query=Writer().pack('I',7778).guid(*gameobjects.modern_guid(guid,0)).finish()
    request=npc_text.request(owner,query)
    native=Writer().pack('I',7778)
    for i in range(8):native.pack('f',1 if i==0 else 0).raw(b'Greeting\0Greeting\0').pack('7I',*([0]*7))
    ids=[10753]+[0]*7;monkeypatch.setattr(npc_text,'broadcasts',lambda _:ids)
    response=packet(('SMSG_QUERY_NPC_TEXT_RESPONSE',npc_text.response(owner,native.finish())))
    actions=[action('gossip_response','SMSG_GOSSIP_MESSAGE',menu),action('npc_query','CMSG_QUERY_NPC_TEXT',query),
        action('npc_reply','SMSG_NPC_TEXT_UPDATE',native.finish()),action('npc_reply','SMSG_NPC_TEXT_UPDATE',native.finish())]
    assert result(codec,op='stateful',character=dict(guid=1,map=0),snapshot=None,gameobjects=[],units=[record],paths=[],broadcasts=ids,actions=actions)==[
        greeting,['CMSG_QUERY_NPC_TEXT',request.hex()],response,None]
