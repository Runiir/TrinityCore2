"""Native core damage fields checked against the pinned WPP442 parser schema.

The request is captured gameplay; damage vectors are explicit native-structure
fixtures, not claims of a captured live damage amount.
"""
import struct
import pytest
from tools.client_compatibility.world.buffer import Reader,Writer
from tools.client_compatibility.world.tests.test_targeted_cast_protocol import CAPTURE
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result

TARGET=CAPTURE['target']['guid']
SERVER_HIGH=(47<<58)|(1<<42)|(57755<<6)|3


def packed(guid):
    octets=guid.to_bytes(8,'little')
    return bytes([sum(bool(v)<<i for i,v in enumerate(octets))])+bytes(v for v in octets if v)


def native(*,target=TARGET,caster=1,spell=57755,damage=1200,overkill=1000,
           school=1,absorbed=0,resisted=0,periodic=0,unused=0,blocked=0,flags=0,debug=0):
    return packed(target)+packed(caster)+struct.pack('<IIIBIIBBIIB',spell,damage,overkill,
        school,absorbed,resisted,periodic,unused,blocked,flags,debug)


def response(codec,body=None,*,owner=1,snapshot=1,units=None,requests=1):
    actions=[{'fn':'cast_request','body':CAPTURE['body']} for _ in range(requests)]
    actions.append({'fn':'combat_response','name':'SMSG_SPELLNONMELEEDAMAGELOG',
                    'body':(native() if body is None else body).hex()})
    return result(codec,op='stateful',character={'guid':owner,'map':0},snapshot={'guid':snapshot},
        units=[CAPTURE['target']] if units is None else units,gameobjects=[],actions=actions)[-1]


def expected(*,serial=1,damage=1200,overkill=1000,absorbed=0,resisted=0,blocked=0,flags=0):
    low,high=CAPTURE['modern_target'] if 'modern_target' in CAPTURE else (174,2305847407260386176)
    return Writer().guid(low,high).guid(1,(2<<58)|(1<<42)).guid(serial,SERVER_HIGH).pack(
        'IIIIIBIII',57755,347658,damage,0,overkill,1,absorbed,resisted,blocked).bits(
        0,1).bits(flags,7).bits(0,1).bits(0,1).bits(0,1).finish()


def test_exact_native_structure_gets_complete_pinned_packet(codec):
    assert response(codec)==['SMSG_SPELL_NON_MELEE_DAMAGE_LOG',expected().hex()]


def test_latest_exact_owned_cast_supplies_identity(codec):
    assert response(codec,requests=2)==['SMSG_SPELL_NON_MELEE_DAMAGE_LOG',expected(serial=2).hex()]
    assert response(codec,requests=0) is None


@pytest.mark.parametrize('case',['caster','snapshot','invisible','other_map','not_unit','wrong_spell','wrong_target'])
def test_damage_stays_bound_to_owned_request_and_visible_target(codec,case):
    kwargs={'caster':{'body':native(caster=2)},'snapshot':{'snapshot':2},'invisible':{'units':[]},
        'other_map':{'units':[{**CAPTURE['target'],'map':1}]},
        'not_unit':{'units':[{**CAPTURE['target'],'kind':5}]},'wrong_spell':{'body':native(spell=57756)},
        'wrong_target':{'body':native(target=TARGET+1),'units':[CAPTURE['target'],
            {**CAPTURE['target'],'guid':TARGET+1}]}}[case]
    assert response(codec,**kwargs) is None


def test_critical_and_mitigation_amounts_retain_native_fields(codec):
    packet=response(codec,native(flags=2,absorbed=150,resisted=25,blocked=100))
    assert packet==['SMSG_SPELL_NON_MELEE_DAMAGE_LOG',expected(flags=2,absorbed=150,resisted=25,blocked=100).hex()]
    r=Reader(bytes.fromhex(packet[1]));r.guid();r.guid();r.guid()
    assert r.unpack('IIIIIBIII')==(57755,347658,1200,0,1000,1,150,25,100)
    assert [r.bits(n) for n in (1,7,1,1,1)]==[0,2,0,0,0];r.end()


@pytest.mark.parametrize('change',[{'damage':2**31},{'overkill':1201},{'school':0},{'school':128},
    {'absorbed':2**31},{'resisted':2**31},{'blocked':2**31},{'periodic':1},{'unused':1},
    {'debug':1},{'flags':1},{'flags':8},{'flags':32},{'flags':64},{'flags':128}])
def test_unsupported_damage_layout_is_explicit_and_codec_remains_healthy(codec,change):
    assert response(codec,native(**change)).get('error')
    assert response(codec)==['SMSG_SPELL_NON_MELEE_DAMAGE_LOG',expected().hex()]


def test_owned_damage_truncations_and_trailing_bytes_are_rejected(codec):
    body=native()
    for length in range(len(body)):assert response(codec,body[:length]).get('error')
    assert response(codec,body+b'\0').get('error')
