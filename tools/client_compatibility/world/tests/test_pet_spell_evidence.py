"""Native pet caster, actual action pair, public buff identity and aura boundaries."""
import copy,json,struct
from pathlib import Path
import pytest
from tools.client_compatibility.pet_spell_evidence import buffs,native_aura,request_checks

FIXTURE=json.loads((Path(__file__).parent/'fixtures/native_trained_pet_manual_spell_ui131.json').read_text())
PET={'guid':FIXTURE['native_pet_guid'],'map':0}


def packed(value):
    data=value.to_bytes(8,'little');return bytes([sum(bool(b)<<i for i,b in enumerate(data))])+bytes(b for b in data if b)


def aura(owner=5,caster=PET['guid'],slot=0,spell=6307):
    body=packed(owner)+struct.pack('<Bi',slot,spell)
    if spell:body+=struct.pack('<HBB',0x41,10,1)+packed(caster)+struct.pack('<i',11)
    return {'direction':'from_native','name':'SMSG_AURA_UPDATE','body':body.hex()}


def packets():
    modern=copy.deepcopy(FIXTURE['request']['packet']);modern.update(session='s',time=10.)
    native={'session':'s','time':10.01,'direction':'to_native','name':'CMSG_PET_ACTION',
        'body':struct.pack('<QIQfff',PET['guid'],0xc10018a3,0,0.,0.,0.).hex()}
    go={'session':'s','time':10.1,'direction':'from_native','name':'SMSG_SPELL_GO',
        'body':(packed(PET['guid'])+packed(PET['guid'])+struct.pack('<Bi',0,6307)).hex()}
    return [modern,native,go]


def test_aura_keeps_exact_owned_unit_native_pet_caster_and_effect_points():
    parsed=native_aura(aura(),5)
    assert parsed=={'unit':5,'all':False,'entries':[{'slot':0,'spell':6307,'flags':0x41,'level':10,
        'applications':1,'caster':PET['guid'],'duration':None,'points':[11]}]}
    packet=aura(spell=0);packet['name']='SMSG_AURA_UPDATE_ALL'
    assert native_aura(packet,5)=={'unit':5,'all':True,'entries':[{'slot':0,'spell':0}]}
    assert native_aura(aura(owner=6),5) is None


@pytest.mark.parametrize('fault',['direction','name','truncated','extra','duplicate','negative','too_many'])
def test_native_aura_rejects_corrupt_or_unattributable_owned_packet(fault):
    p=aura();body=bytes.fromhex(p['body'])
    if fault=='direction':p['direction']='to_client'
    elif fault=='name':p['name']='SMSG_SPELL_GO'
    elif fault=='truncated':p['body']=body[:-1].hex()
    elif fault=='extra':p['body']=(body+b'x').hex()
    elif fault=='duplicate':p['body']=(body+body[len(packed(5)):]).hex()
    elif fault=='negative':p['body']=(packed(5)+struct.pack('<Bi',0,-1)).hex()
    else:p['body']=(packed(5)+b''.join(struct.pack('<Bi',i,0) for i in range(256))).hex()
    with pytest.raises((ValueError,struct.error)):native_aura(p,5)


def test_actual_modern_shape_and_owned_native_pair_with_matching_pet_completion():
    checks,proof=request_checks(iter(packets()),'s',9.,12.,PET)
    assert len(checks)==9 and all(checks.values())
    assert proof['completed'][0]['decoded']['caster']==PET['guid']


@pytest.mark.parametrize('fault',['foreign_session','before','missing_native','missing_go','duplicate_native',
    'duplicate_go','foreign_pet','wrong_native_spell','wrong_completion_spell','foreign_caster','early_go',
    'late_go','abandon','other_native','other_modern','failed'])
def test_cast_cannot_pass_with_unpaired_unowned_duplicate_or_failed_outcome(fault):
    rows=packets()
    if fault=='foreign_session':rows[1]['session']='other'
    elif fault=='before':rows[0]['time']=8.
    elif fault=='missing_native':rows.pop(1)
    elif fault=='missing_go':rows.pop()
    elif fault=='duplicate_native':rows.append(copy.deepcopy(rows[1]))
    elif fault=='duplicate_go':rows.append(copy.deepcopy(rows[2]))
    elif fault=='foreign_pet':rows[1]['body']=struct.pack('<QIQfff',PET['guid']+1,0xc10018a3,0,0.,0.,0.).hex()
    elif fault=='wrong_native_spell':rows[1]['body']=struct.pack('<QIQfff',PET['guid'],0xc1000c26,0,0.,0.,0.).hex()
    elif fault in ('wrong_completion_spell','foreign_caster'):
        rows[2]['body']=(packed(6 if fault=='foreign_caster' else PET['guid'])+packed(PET['guid'])+
            struct.pack('<Bi',0,3110 if fault=='wrong_completion_spell' else 6307)).hex()
    elif fault=='early_go':rows[2]['time']=10.005
    elif fault=='late_go':rows[2]['time']=11.99;rows[1]['time']=1.;rows[0]['time']=.99
    elif fault in ('abandon','other_native','other_modern'):
        rows.append({'session':'s','time':10.02,'name':'CMSG_PET_ABANDON' if fault=='abandon' else 'CMSG_CAST_SPELL',
            'direction':'from_client' if fault=='other_modern' else 'to_native','body':'00'})
    else:rows.append({'session':'s','time':10.02,'name':'SMSG_CAST_FAILED','direction':'from_native',
        'body':struct.pack('<BiB',0,6307,1).hex()})
    checks,_=request_checks(iter(rows),'s',0. if fault=='late_go' else 9.,12.,PET)
    assert not all(checks.values())


@pytest.mark.parametrize('value',[None,False,'6307',[True],[-1],[0],{'6307':True}])
def test_public_buff_reader_refuses_missing_or_non_spell_id_lists(value):
    with pytest.raises(ValueError):buffs({'buffs':value})


def test_public_buff_reader_accepts_empty_lua_table_and_numeric_spell_ids():
    assert buffs({'buffs':{}})==buffs({'buffs':[]})==[]
    assert buffs({'buffs':[6307]})==[6307]
