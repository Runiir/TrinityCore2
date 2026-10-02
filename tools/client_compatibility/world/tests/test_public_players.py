"""Visible players use public roots and lose target authority when removed."""
import struct
from copy import deepcopy
from tools.client_compatibility.world.buffer import Reader,Writer,player_high
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_inventory_packets import mask


PROFILE={'guid':2,'name':'Harnesstwo','gender':0}


def snapshot():
    return {'guid':2,'kind':4,'map':0,'flags':{'self':0},
        'fields':{INDEX['UNIT_FIELD_BYTES_0']:257,INDEX['UNIT_FIELD_LEVEL']:1,
            INDEX['UNIT_FIELD_HEALTH']:100,INDEX['UNIT_FIELD_MAXHEALTH']:100,
            INDEX['OBJECT_FIELD_SCALE_X']:0x3f800000,INDEX['PLAYER_VISIBLE_ITEM_1_ENTRYID']:39},
        'movement':{'flags':0,'flags2':0,'position':[-8912.37,-140,82.12,2.33],
            'time':42,'pitch':0,'speeds':[2.5,7,4.5,4.72,2.5,7,4.5,3.14,3.14]}}


def native_values(w,fields):
    masks=[0]*(max(fields)//32+1)
    for i in fields:masks[i//32]|=1<<(i%32)
    w.pack('B',len(masks)).pack('I'*len(masks),*masks)
    for i in sorted(fields):w.pack('I',fields[i])
    return w.finish()


def native_create(fields):
    # Native kind=4, nonself living movement from the pinned Cata layout.
    w=Writer().pack('HIB',0,1,1).raw(bytes([1,2])).pack('B',4)
    w.bits(0,7).bits(1,1).bits(0,24).bits(0,6)
    for bit in [1,0,0,0,0,0,1,0,0,1,0,0,0,0,0,1,0,0,1]:w.bits(bit,1)
    w.pack('3f',4.5,2.5,82.12).pack('2f',-8912.37,3.14).pack('B',3)
    w.pack('3f',4.72,-140,2.5).pack('If4f',42,3.14,7,2.33,7,4.5)
    return native_values(w,fields)


def test_public_create_has_player_roots_without_owner_movement_extras(codec):
    body=result(codec,op='object_block',kind='public_player',snapshot=snapshot(),character=PROFILE)
    r=Reader(bytes.fromhex(body));assert r.unpack('B')==(1,);assert r.guid()==(2,player_high())
    assert r.unpack('B')==(6,);assert {i for i in range(19) if r.bits(1)}=={0,4}
    assert r.guid()==(2,player_high());assert r.unpack('4I')==(0,0,0,42)
    r.unpack('4f');r.unpack('ffII');assert r.bits(8)==0;r.unpack('9f');r.unpack('If17f')
    assert r.bits(1)==0;assert r.unpack('I')==(0,)
    size=r.unpack('I')[0];data=r.raw(size);r.end()
    assert data[:6]==bytes([0,0,5,6,255,1]);assert b'Harnesstwo' in data


def test_public_create_does_not_serialize_inventory_skills_gold_xp_or_owner_stats(codec):
    original=snapshot();changed=deepcopy(original)
    for name in ['PLAYER_XP','PLAYER_NEXT_LEVEL_XP','PLAYER_FIELD_COINAGE','PLAYER_SKILL_RANK_0',
        'PLAYER_FIELD_RESEARCH_SITE_1','PLAYER_FIELD_INV_SLOT_HEAD','UNIT_FIELD_STAT0','UNIT_FIELD_ATTACK_POWER']:
        changed['fields'][INDEX[name]]=123456
    args={'op':'object_block','kind':'public_player','character':PROFILE}
    assert result(codec,**args,snapshot=original)==result(codec,**args,snapshot=changed)
    for bad in [{**PROFILE,'guid':3},{**PROFILE,'gender':2},{**PROFILE,'name':''}]:
        assert 'error' in codec(**{**args,'character':bad},snapshot=original)
    changed=deepcopy(original);changed['flags']['self']=1
    assert 'error' in codec(**args,snapshot=changed)


def test_public_sparse_equipment_excludes_private_slot_root(codec):
    fields={INDEX['PLAYER_VISIBLE_ITEM_1_ENTRYID']:0,INDEX['PLAYER_FIELD_INV_SLOT_HEAD']:10,
        INDEX['PLAYER_FIELD_INV_SLOT_HEAD']+1:0x40000000}
    block=result(codec,op='inventory_update',snapshot={'guid':2,'fields':fields},changed=fields,visibility=0)
    r=Reader(bytes.fromhex(block));assert r.unpack('B')==(0,);assert r.guid()==(2,player_high())
    assert r.unpack('I')[0]==len(r.data)-r.pos;assert r.unpack('BBBI')==(0,0,3,1<<6)
    assert mask(r,5)=={68,69};assert r.bits(1)==0;r.align();assert r.bits(4)==3
    assert r.unpack('i')==(0,);r.end()
    private={k:v for k,v in fields.items() if k!=INDEX['PLAYER_VISIBLE_ITEM_1_ENTRYID']}
    assert result(codec,op='inventory_update',snapshot={'guid':2,'fields':fields},changed=private,visibility=0)==''


def test_native_visibility_create_update_remove_bounds_selection(codec):
    creation=native_create(snapshot()['fields'])
    change=native_values(Writer().pack('HIB',0,1,0).raw(bytes([1,2])),{INDEX['UNIT_FIELD_HEALTH']:80})
    removed=Writer().pack('HIBI',0,1,3,1).raw(bytes([1,2])).finish()
    selected=Writer().guid(2,player_high()).finish()
    actions=[('object_updates','SMSG_UPDATE_OBJECT',creation),('combat_request','CMSG_SET_SELECTION',selected),
        ('object_updates','SMSG_UPDATE_OBJECT',change),('object_updates','SMSG_UPDATE_OBJECT',removed),
        ('combat_request','CMSG_SET_SELECTION',selected)]
    args={'op':'stateful','character':{'guid':1,'name':'Harnessone','gender':0,'map':0},
        'snapshot':{'guid':1,'kind':4,'map':0,'fields':{}},'players':[PROFILE],
        'actions':[{'fn':fn,'name':name,'body':body.hex()} for fn,name,body in actions]}
    replies=result(codec,**args)
    assert replies[0][0]=='SMSG_UPDATE_OBJECT'
    assert replies[1]==['CMSG_SET_SELECTION',struct.pack('<Q',2).hex()]
    assert replies[2][0]=='SMSG_UPDATE_OBJECT' and replies[3][0]=='SMSG_UPDATE_OBJECT'
    assert replies[4] is None
    assert 'error' in result(codec,**{**args,'players':[]})[0]
    assert 'error' in result(codec,**{**args,'players':[PROFILE,PROFILE]})[0]
