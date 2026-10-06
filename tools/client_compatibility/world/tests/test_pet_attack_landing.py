"""Captured teleport acknowledgement admits floor settling without horizontal drift."""
import copy,json
from pathlib import Path
import pytest
from tools.client_compatibility.pet_attack_landing import acknowledgement,landing_checks

F=json.loads((Path(__file__).parent/'fixtures/owned_pet_landing_ack_ui139.json').read_text())


@pytest.mark.parametrize('fault',['none','missing_client_ack','missing_native_ack','duplicate_client_ack',
    'wrong_owner','wrong_counter','wrong_native_body','wrong_session','outside_window','wrong_destination'])
def test_landing_requires_exact_owned_client_and_native_acknowledgement(fault):
    rows=copy.deepcopy(F['packets']);owner=F['owner'];initial=F['initial'].copy()
    if fault=='missing_client_ack':rows.pop(1)
    elif fault=='missing_native_ack':rows.pop(2)
    elif fault=='duplicate_client_ack':rows.append(copy.deepcopy(rows[1]))
    elif fault=='wrong_owner':owner=6
    elif fault=='wrong_counter':rows[1]['body']=rows[1]['body'][:10]+'03000000'+rows[1]['body'][18:]
    elif fault=='wrong_native_body':rows[2]['body']+='00'
    elif fault=='wrong_session':rows[2]['session']='other'
    elif fault=='outside_window':rows[1]['time']=F['until']+1
    elif fault=='wrong_destination':initial[0]+=1
    args=(rows,F['session'],F['since'],F['until'],owner,initial)
    if fault=='none':assert acknowledgement(*args)['native_ack']['body']==F['packets'][2]['body']
    else:
        with pytest.raises(RuntimeError,match='one exact owned teleport'):acknowledgement(*args)


@pytest.mark.parametrize('changed',[None,0,1,2,3,4])
def test_floor_difference_is_bounded_and_xy_facing_map_stay_fixed(changed):
    accepted=F['settled'].copy()
    if changed is not None:accepted[changed]+=1
    assert all(landing_checks(F['initial'],accepted).values()) is (changed is None)
