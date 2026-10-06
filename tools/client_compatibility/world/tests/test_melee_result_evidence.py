import pytest
import struct
from tools.client_compatibility.melee_result_evidence import translated,pairs,public_events,health_checks
from tools.client_compatibility.world.tests.test_owned_melee_results import CAPTURE,MODERN,VICTIM


def test_captured_physical_vector_has_independent_exact_oracle():
    result=translated(CAPTURE,0)
    assert result['body']==MODERN and result['attacker']==5 and result['victim']==VICTIM
    assert result['damage']==6 and result['overkill']==-1 and result['hit_info']==2


def test_foreign_optional_layout_does_not_enter_owned_damage_parser():
    # Same native opcode can broadcast nearby NPC combat with another layout.
    body=bytearray(CAPTURE);body[5]=6;struct.pack_into('<I',body,0,0x20)
    native={'name':'SMSG_ATTACKER_STATE_UPDATE','direction':'from_native','time':1.,'body':bytes(body).hex()}
    assert pairs([native],5,VICTIM,0)==([],[])


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


@pytest.mark.parametrize('fault',[None,'source','destination','old_sequence','amount','overkill','school','timestamp',
    'critical','offhand','glancing','crushing','missing_delivery'])
def test_public_damage_requires_owned_identity_freshness_and_exact_native_outcome(fault):
    event={'event':'SWING_DAMAGE','sequence':2,'source_guid':'player','destination_guid':'target',
        'amount':6,'overkill':-1,'school':1,'timestamp':1.1,
        'critical':False,'offhand':False,'glancing':False,'crushing':False}
    matched=[{'native':{'time':1.},'expected':{'damage':6,'overkill':-1,'hit_info':2},'client':{'time':1.05}}]
    if fault in ('source','destination'):event[fault+'_guid']='another'
    elif fault=='old_sequence':event['sequence']=1
    elif fault in ('amount','overkill','school'):event[fault]=99
    elif fault=='timestamp':event['timestamp']=3.
    elif fault in ('critical','offhand','glancing','crushing'):event[fault]=True
    elif fault=='missing_delivery':matched[0]['client']=None
    assert bool(public_events({'events':[event]},1,matched,'player','target'))==(fault is None)


@pytest.mark.parametrize('fault',[None,'calculated_only','foreign_damage','stale_public_health','dead_target','missing_delivery'])
def test_applied_damage_requires_living_target_and_exact_native_public_health_loss(fault):
    before,after,public,foreign=142,136,136,[]
    matched=[{'expected':{'damage':6},'client':{'time':1.1}}]
    if fault=='calculated_only':after=public=142
    elif fault=='foreign_damage':foreign=[{'attacker':9}]
    elif fault=='stale_public_health':public=142
    elif fault=='dead_target':after=public=0
    elif fault=='missing_delivery':matched[0]['client']=None
    assert all(health_checks(before,after,matched,public,foreign).values())==(fault is None)
