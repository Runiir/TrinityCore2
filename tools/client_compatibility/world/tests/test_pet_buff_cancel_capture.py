"""An ordinary cancel request must refer to the current owned pet's observed buff."""
import copy,json
from pathlib import Path
from types import SimpleNamespace
import pytest
from tools.client_compatibility.interaction_pet_buff_cancel_capture import authority
from tools.client_compatibility.interaction_pet_command_probe import expected_guid
from tools.client_compatibility.world.objects import INDEX

FIXTURE=json.loads((Path(__file__).parent/'fixtures/native_trained_pet_manual_spell_ui131.json').read_text())


def source():
    pet=copy.deepcopy(FIXTURE['native_pet_create']);pet['fields']={int(k):v for k,v in pet['fields'].items()}
    aura={'spell':6307,'caster':pet['guid']}
    t=SimpleNamespace(fixture={'guid':5},guid='Player-1-00000005')
    o=SimpleNamespace(pet=pet,present=lambda:True,auras={0:aura})
    sample={'ui_clean':True,'probe':{'owner_guid':t.guid,'pet_guid':expected_guid(pet)}}
    return t,o,sample,{'buffs':[6307]}


def test_current_owned_native_caster_and_public_buff_allow_capture():
    t,o,sample,state=source();assert authority(t,o,sample,state) is o.auras[0]


@pytest.mark.parametrize('fault',['actor','absent','kind','owner','number','missing_aura','duplicate_aura',
    'foreign_caster','missing_public_buff','duplicate_public_buff','ui_error','public_owner','public_pet'])
def test_stale_or_unowned_cancel_authority_is_rejected(fault):
    t,o,sample,state=source()
    if fault=='actor':t.fixture['guid']=4
    elif fault=='absent':o.present=lambda:False
    elif fault=='kind':o.pet['kind']=4
    elif fault=='owner':o.pet['fields'][INDEX['UNIT_FIELD_SUMMONEDBY']]=4
    elif fault=='number':o.pet['fields'][INDEX['UNIT_FIELD_PETNUMBER']]=1
    elif fault=='missing_aura':o.auras={}
    elif fault=='duplicate_aura':o.auras[1]=copy.deepcopy(o.auras[0])
    elif fault=='foreign_caster':o.auras[0]['caster']+=1
    elif fault=='missing_public_buff':state['buffs']=[]
    elif fault=='duplicate_public_buff':state['buffs']=[6307,6307]
    elif fault=='ui_error':sample['ui_clean']=False
    elif fault=='public_owner':sample['probe']['owner_guid']='Player-1-00000004'
    else:sample['probe']['pet_guid']='foreign'
    with pytest.raises(RuntimeError):authority(t,o,sample,state)
