import pytest
from tools.client_compatibility.melee_result_evidence import translated,pairs
from tools.client_compatibility.world.tests.test_owned_melee_results import CAPTURE,MODERN,VICTIM


def test_captured_physical_vector_has_independent_exact_oracle():
    result=translated(CAPTURE,0)
    assert result['body']==MODERN and result['attacker']==5 and result['victim']==VICTIM
    assert result['damage']==6 and result['overkill']==-1 and result['hit_info']==2


@pytest.mark.parametrize('fault',[None,'missing','duplicate','wrong_body','too_late'])
def test_packet_pairing_requires_one_timely_exact_client_delivery(fault):
    native={'name':'SMSG_ATTACKER_STATE_UPDATE','direction':'from_native','time':1.,'body':CAPTURE.hex()}
    delivered={'name':native['name'],'direction':'to_client','time':1.1,'body':MODERN}
    rows=[native,delivered]
    if fault=='missing':rows.pop()
    elif fault=='duplicate':rows.append({**delivered,'time':1.2})
    elif fault=='wrong_body':delivered['body']=MODERN+'00'
    elif fault=='too_late':delivered['time']=3.1
    matched,orphaned=pairs(rows,5,VICTIM,0)
    assert len(matched)==1
    assert bool(matched[0]['client'])==(fault in (None,'duplicate'))
    assert bool(orphaned)==(fault in ('duplicate','wrong_body','too_late'))
