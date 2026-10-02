"""Independent pinned UnitData mask/order checks for real character sheet fields."""
import struct
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.buffer import Reader,Writer,player_high
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result,stateful,action
from tools.client_compatibility.world.tests.test_inventory_packets import read_block,mask


def bits_float(n):return struct.unpack('<I',struct.pack('<f',n))[0]


def native_values():
    return {INDEX['UNIT_FIELD_STAT0']:5830,INDEX['UNIT_FIELD_POSSTAT0']:5500,
        INDEX['UNIT_FIELD_NEGSTAT0']:0xfffffff9,INDEX['UNIT_FIELD_STAT0']+1:300,
        INDEX['UNIT_FIELD_RESISTANCES']:20458,INDEX['UNIT_FIELD_RESISTANCEBUFFMODSPOSITIVE']:20000,
        INDEX['UNIT_FIELD_RESISTANCEBUFFMODSNEGATIVE']:0xfffffff6,
        INDEX['UNIT_FIELD_MINDAMAGE']:bits_float(6983.640625),INDEX['UNIT_FIELD_MAXDAMAGE']:bits_float(8746.9794921875),
        INDEX['UNIT_FIELD_ATTACK_POWER']:12000,INDEX['UNIT_FIELD_ATTACK_POWER_MOD_NEG']:0xfffffffb,
        INDEX['UNIT_FIELD_ATTACK_POWER_MULTIPLIER']:bits_float(.1)}


def test_create_stats_preserve_native_effective_values_signed_buffs_and_damage(codec):
    v=result(codec,op='object_values',snapshot={'guid':1,'fields':native_values()},character={})['UnitData']
    assert v['Stats'][:2]==[5830,300] and v['StatPosBuff'][0]==5500 and v['StatNegBuff'][0]==-7
    assert v['Resistances'][0]==20458 and v['ResistanceBuffModsNegative'][0]==-10
    assert v['MinDamage']==6983.640625 and v['MaxDamage']==8746.9794921875
    assert v['AttackPower']==12000 and v['AttackPowerModNeg']==-5


def test_sparse_stats_interleave_buffs_per_element_and_use_array_parent_masks(codec):
    fields=native_values()
    block=result(codec,op='unit_update',snapshot={'guid':1,'map':0,'fields':fields},changed=fields,character={},visibility=1)
    r=read_block(block,(1,player_high()),1<<5)
    assert mask(r,8)=={32,53,54,64,82,84,85,176,177,178,182,187,192,193,200,207}
    r.align();assert r.unpack('2f')==(6983.640625,8746.9794921875)
    assert r.unpack('2i')==(12000,-5);assert abs(r.unpack('f')[0]-.1)<1e-6
    # Stats[0], positive[0], negative[0], Stats[1]. Mask-index sorting is wrong.
    assert r.unpack('4i')==(5830,5500,-7,300)
    assert r.unpack('3i')==(20458,20000,-10);r.end()
    assert result(codec,op='unit_update',snapshot={'guid':1,'fields':fields},changed={},character={},visibility=1)==''
    assert result(codec,op='unit_update',snapshot={'guid':1,'fields':fields},changed=fields,character={},visibility=0)==''


def test_zero_power_and_health_change_survive_with_public_array_parent(codec):
    fields={INDEX['UNIT_FIELD_HEALTH']:0,INDEX['UNIT_FIELD_POWER1']:0,INDEX['UNIT_FIELD_MAXPOWER1']:100,
        INDEX['UNIT_FIELD_POWER1']+1:10,INDEX['UNIT_FIELD_MAXPOWER1']+1:120}
    block=result(codec,op='unit_update',snapshot={'guid':1,'map':0,'fields':fields},changed=fields,character={},visibility=0)
    r=Reader(bytes.fromhex(block));assert r.unpack('B')==(0,) and r.guid()==(1,player_high())
    assert r.unpack('I')[0]==len(r.data)-r.pos and r.unpack('BBBI')==(0,0,3,1<<5)
    assert mask(r,8)=={0,5,117,138,139,148,149};r.align()
    assert r.unpack('q')==(0,) and r.unpack('4i')==(0,100,10,120);r.end()


def test_native_equipment_stat_delta_reaches_dispatcher(codec):
    fields={INDEX['UNIT_FIELD_STAT0']:5830,INDEX['UNIT_FIELD_RESISTANCES']:20458}
    words=[0]*((max(fields)//32)+1)
    for i in fields:words[i//32]|=1<<(i%32)
    w=Writer().pack('HI',0,1).pack('B',0).raw(bytes([1,1])).pack('B',len(words)).pack('I'*len(words),*words)
    for i in sorted(fields):w.pack('I',fields[i])
    reply=stateful(codec,{'guid':1,'map':0},[action('object_updates','SMSG_UPDATE_OBJECT',w.finish())],snapshot={'guid':1,'map':0,'fields':{}})[0]
    assert reply[0]=='SMSG_UPDATE_OBJECT';r=Reader(bytes.fromhex(reply[1]))
    assert r.unpack('HI')==(0,1) and r.bits(1)==1 and r.bits(1)==0
    size=r.unpack('I')[0];block=r.raw(size);r.end()
    r=read_block(block.hex(),(1,player_high()),1<<5)
    assert mask(r,8)=={176,177,192,193};r.align();assert r.unpack('2i')==(5830,20458);r.end()
