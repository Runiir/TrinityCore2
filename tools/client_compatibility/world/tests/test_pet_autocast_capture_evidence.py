"""A foreign, stale, hidden or already-toggled control cannot be used for capture."""
import copy,json
from pathlib import Path
import pytest
from tools.client_compatibility.pet_autocast_capture_evidence import button,native_buttons,request_checks
from tools.client_compatibility.interaction_pet_command_probe import expected_guid
from tools.client_compatibility.interaction_pet_react_modes import suite

ACTUAL=json.loads((Path(__file__).parent/'fixtures/native_trained_pet_defensive_ui128.json').read_text())
PET={'guid':ACTUAL['native_pet_guid'],'map':0}


def probe():return {'owner_guid':'Player-1-00000005','pet_guid':expected_guid(PET),'actions':[
    {'slot':slot,'spell_id':spell,'name':name,'available':True,'is_token':False,'autocast_allowed':True,
        'autocast_enabled':True,'frame':{'button':'PetActionButton'+str(slot),'available':True,
            'visible':True,'enabled':True,'x':17000,'y':59000}}
    for spell,slot,name in [(3110,4,'Firebolt'),(6307,5,'Blood Pact')]]}


def test_both_actual_native_enabled_spells_match_stock_owned_controls():
    catalog={'packet':ACTUAL['native_catalog_packet']};rows=native_buttons(catalog,PET)
    for spell,slot in [(3110,4),(6307,5)]:
        assert rows[slot-1]=={'slot':slot,'spell_id':spell,'action_type':0xc1}
        row,point=button(probe(),PET,spell,True);assert row['slot']==slot and point==[332,648]


@pytest.mark.parametrize('fault',['owner','pet','missing','duplicate','token','slot','spell','not_autocast',
    'already_off','flag_integer','unavailable','hidden','disabled','wrong_frame','outside','edge','bool_coord'])
def test_refuse_unattributable_or_wrong_state_autocast_button_before_input(fault):
    p=probe();r=p['actions'][0];f=r['frame']
    if fault=='owner':p['owner_guid']='Player-1-00000004'
    elif fault=='pet':p['pet_guid']='Pet-0-1-0-0-416-0000000001'
    elif fault=='missing':p['actions'].pop(0)
    elif fault=='duplicate':p['actions'].append(copy.deepcopy(r))
    elif fault=='token':r['is_token']=True
    elif fault=='slot':r['slot']=5
    elif fault=='spell':r['spell_id']=91702
    elif fault=='not_autocast':r['autocast_allowed']=False
    elif fault=='already_off':r['autocast_enabled']=False
    elif fault=='flag_integer':r['autocast_enabled']=1
    elif fault=='unavailable':r['available']=False
    elif fault=='hidden':f['visible']=False
    elif fault=='disabled':f['enabled']=False
    elif fault=='wrong_frame':f['button']='ActionButton4'
    elif fault=='outside':f['x']=65536
    elif fault=='edge':f['x']=65535
    else:f['x']=True
    with pytest.raises(RuntimeError):button(p,PET,3110,True)


@pytest.mark.parametrize('fault',['foreign','outside','no_body','empty','nonhex','odd','native','abandon','duplicate'])
def test_raw_capture_requires_current_session_window_body_and_zero_native_mutation(fault):
    p={'session':'owned','time':10,'name':'CMSG_PET_SPELL_AUTOCAST','direction':'from_client','body':'0102'};rows=[p]
    assert all(request_checks(iter(rows),'owned',9,11)[0].values())
    if fault=='foreign':p['session']='foreign'
    elif fault=='outside':p['time']=8
    elif fault=='no_body':p.pop('body')
    elif fault=='empty':p['body']=''
    elif fault=='nonhex':p['body']='zz'
    elif fault=='odd':p['body']='012'
    elif fault=='native':rows.append({**p,'direction':'to_native'})
    elif fault=='abandon':rows.append({**p,'name':'CMSG_PET_ABANDON'})
    else:rows.extend([dict(p),dict(p)])
    assert not all(request_checks(iter(rows),'owned',9,11)[0].values())


@pytest.mark.parametrize('fault',['foreign','modern','mode'])
def test_native_autocast_baseline_must_be_current_owned_real_assist_catalog(fault):
    c={'packet':copy.deepcopy(ACTUAL['native_catalog_packet'])};p=dict(PET)
    if fault=='foreign':p['guid']+=1
    elif fault=='modern':c['packet']['direction']='to_client'
    else:
        b=bytearray.fromhex(c['packet']['body']);b[14]=1;c['packet']['body']=b.hex()
    with pytest.raises(RuntimeError):native_buttons(c,p)


@pytest.mark.parametrize('sequence,capture',[
    (((3,'fixture.pet_assist_restore'),),None),(((0,'pets.passive'),(3,'pets.assist')),lambda *a:None),
    (((1,'pets.defensive'),),lambda *a:None)])
def test_capture_hook_cannot_bypass_exact_original_assist_restoration_sequence(sequence,capture):
    with pytest.raises(ValueError):suite(None,None,None,sequence=sequence,capture=capture)
