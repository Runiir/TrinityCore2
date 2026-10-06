"""A cancellation must preserve the submitted owner and current native pet identity."""
import copy,json,struct
from pathlib import Path
import pytest
from tools.client_compatibility.pet_spell_evidence import cancel_request_checks

F=json.loads((Path(__file__).parent/'fixtures/native_owned_pet_aura_cancel_ui133.json').read_text())


def packets():
    modern={**F['modern_request'],'time':10,'session':'s'}
    native={**F['ignored_native_player_request'],'time':10.1,'session':'s',
        'name':'CMSG_PET_CANCEL_AURA','body':struct.pack('<QI',F['native_pet_guid'],6307).hex()}
    return [modern,native]


def check(rows):return cancel_request_checks(rows,'s',9,12,F['native_pet_create'])[0]


def test_exact_owner_and_current_native_pet_cancel_pair():assert all(check(packets()).values())


@pytest.mark.parametrize('fault',['foreign_pet','wrong_spell','player_cancel','missing_native','duplicate_native',
    'duplicate_modern','foreign_session','before_window','out_of_order','extra_cast','extra_abandon'])
def test_changed_or_unattributable_cancel_cannot_prove_cleanup(fault):
    rows=packets()
    if fault=='foreign_pet':rows[1]['body']=struct.pack('<QI',F['native_pet_guid']+1,6307).hex()
    elif fault=='wrong_spell':rows[1]['body']=struct.pack('<QI',F['native_pet_guid'],3110).hex()
    elif fault=='player_cancel':rows[1]['name']='CMSG_CANCEL_AURA'
    elif fault=='missing_native':rows.pop()
    elif fault=='duplicate_native':rows.append(copy.deepcopy(rows[1]))
    elif fault=='duplicate_modern':rows.append(copy.deepcopy(rows[0]))
    elif fault=='foreign_session':rows[1]['session']='other'
    elif fault=='before_window':rows[1]['time']=8
    elif fault=='out_of_order':rows[1]['time']=9.5
    else:rows.append({**rows[1],'name':'CMSG_CAST_SPELL' if fault=='extra_cast' else 'CMSG_PET_ABANDON'})
    assert not all(check(rows).values())
