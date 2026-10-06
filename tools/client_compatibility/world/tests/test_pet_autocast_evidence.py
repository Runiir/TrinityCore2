"""Local flags or saved rows cannot substitute for exact native switch/delivery pairs."""
import copy,json,struct
from pathlib import Path
import pytest
from tools.client_compatibility.pet_autocast_evidence import request_checks,saved_buttons,native_catalog,catalog_delivery

F=json.loads((Path(__file__).parent/'fixtures/native_trained_pet_autocast_ui130.json').read_text())
PET={'guid':F['native_pet_guid'],'map':0}


def rows():
    p=F['requests'][0]['packet'];return [dict(p,time=10),{'session':p['session'],'time':10.1,'direction':'to_native',
        'name':'CMSG_PET_SET_ACTION','body':struct.pack('<QII',PET['guid'],3,0x81000c26).hex()}]


def test_actual_request_identity_and_independent_saved_native_delivered_catalog():
    r=rows();assert all(request_checks(r,r[0]['session'],9,11,PET,3110,False)[0].values())
    c={'packet':F['actual_reload_native_catalog']};data=native_catalog(c)
    assert data['guid']==PET['guid'] and data['react']==3 and data['command']==1
    assert data['buttons']==saved_buttons({'abdata':F['saved_baseline_abdata']})
    assert catalog_delivery([F['actual_reload_modern_catalog']],F['actual_reload_native_catalog']['session'],c,PET)==[F['actual_reload_modern_catalog']]


@pytest.mark.parametrize('fault',['foreign_modern','foreign_native','outside','late','duplicate_modern',
    'duplicate_native','missing_modern','missing_native','wrong_native_flag','wrong_native_slot','wrong_pet',
    'wrong_modern_flag','truncated_modern','trailing_modern','abandon','extra_native_action'])
def test_switch_requires_current_exact_owned_native_delivery_and_no_extra_action(fault):
    r=rows();session=r[0]['session'];p=dict(PET)
    if fault=='foreign_modern':r[0]['session']='foreign'
    elif fault=='foreign_native':r[1]['session']='foreign'
    elif fault=='outside':r[0]['time']=8
    elif fault=='late':r[1]['time']=12
    elif fault=='duplicate_modern':r.append(dict(r[0]))
    elif fault=='duplicate_native':r.append(dict(r[1]))
    elif fault=='missing_modern':r.pop(0)
    elif fault=='missing_native':r.pop()
    elif fault=='wrong_native_flag':r[1]['body']=struct.pack('<QII',PET['guid'],3,0xc1000c26).hex()
    elif fault=='wrong_native_slot':r[1]['body']=struct.pack('<QII',PET['guid'],4,0x81000c26).hex()
    elif fault=='wrong_pet':p['guid']+=1
    elif fault=='wrong_modern_flag':r[0]['body']=F['requests'][1]['packet']['body']
    elif fault=='truncated_modern':r[0]['body']=r[0]['body'][:-2]
    elif fault=='trailing_modern':r[0]['body']+='00'
    else:r.append({**r[1],'name':'CMSG_PET_ABANDON' if fault=='abandon' else 'CMSG_PET_ACTION'})
    assert not all(request_checks(r,session,9,13,p,3110,False)[0].values())


@pytest.mark.parametrize('fault',['foreign_session','late','duplicate','wrong_guid','wrong_bar_flag',
    'wrong_learned_flag','truncated','trailing','oversized_count'])
def test_native_catalog_requires_exact_current_modern_payload_delivery(fault):
    c={'packet':copy.deepcopy(F['actual_reload_native_catalog'])};m=copy.deepcopy(F['actual_reload_modern_catalog']);r=[m]
    session=c['packet']['session'];body=bytearray.fromhex(m['body'])
    if fault=='foreign_session':m['session']='foreign'
    elif fault=='late':m['time']=c['packet']['time']+2.1
    elif fault=='duplicate':r.append(dict(m))
    elif fault=='wrong_guid':body[2]^=1
    elif fault=='wrong_bar_flag':body[6+11+3*4+3]^=0x40
    elif fault=='wrong_learned_flag':body[-1]^=0x40
    elif fault=='truncated':body=body[:-1]
    elif fault=='trailing':body+=b'x'
    else:struct.pack_into('<I',body,6+11+40,0xffffffff)
    m['body']=body.hex();found=catalog_delivery(r,session,c,PET)
    assert len(found)!=1


@pytest.mark.parametrize('value',['','193 3110','-1 2 '+'1 0 '*9,'256 2 '+'1 0 '*9,'193 16777216 '+'1 0 '*9])
def test_saved_bar_requires_all_ten_exact_native_width_pairs(value):
    with pytest.raises(ValueError):saved_buttons({'abdata':value})
