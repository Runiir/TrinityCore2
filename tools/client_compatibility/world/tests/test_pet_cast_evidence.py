"""Firebolt admission rejects missing, duplicate, stale and wrong native delivery."""
import copy,struct
import pytest
from tools.client_compatibility.pet_cast_evidence import firebolt_checks
from tools.client_compatibility.world.buffer import Reader
from tools.client_compatibility.world.tests.test_pet_cast_protocol import F,CASTS,controlled,request
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec


@pytest.mark.parametrize('fault',['none','missing','duplicate','late','other_session','wrong_visual',
    'wrong_cast_identity','wrong_native_hit','extra_delivery'])
def test_firebolt_admission_requires_exact_delivery_and_paired_cast_lifetime(codec,fault):
    emitted=controlled(codec,[request(c['packet']) for c in CASTS]);rows=[]
    for index,(c,out) in enumerate(zip(CASTS,emitted[1:])):
        p={**c['packet'],'time':11+index*3,'session':'owned','direction':'from_native'}
        rows.extend([p,{**p,'body':out['packet'][1],'direction':'to_client','time':p['time']+.1}])
    clients=[r for r in rows if r['direction']=='to_client' and r['name']=='SMSG_SPELL_GO']
    victim=clients[1]
    if fault=='missing':rows.remove(victim)
    elif fault=='duplicate':rows.append(copy.deepcopy(victim))
    elif fault=='late':victim['time']+=2
    elif fault=='other_session':victim['session']='other'
    elif fault in ('wrong_visual','wrong_cast_identity'):
        body=bytearray.fromhex(victim['body']);r=Reader(body);r.guid();r.guid()
        if fault=='wrong_cast_identity':body[r.pos+2]^=64
        else:r.guid();r.guid();struct.pack_into('<I',body,r.pos+4,67)
        victim['body']=body.hex()
    elif fault=='wrong_native_hit':
        native=rows[6];body=bytearray.fromhex(native['body'])
        before=struct.pack('<Q',F['native_target']['guid']);offset=body.index(before)
        body[offset:offset+8]=struct.pack('<Q',F['native_target']['guid']+1);native['body']=body.hex()
    elif fault=='extra_delivery':
        extra=copy.deepcopy(victim);extra['time']+=2.1;rows.append(extra)
    checks,pairs=firebolt_checks(rows,'owned',10,50,F['native_pet'],F['native_target'])
    assert (all(checks.values())) is (fault=='none')
    if fault=='none':assert len(pairs)==7 and all(p['client'] for p in pairs)
