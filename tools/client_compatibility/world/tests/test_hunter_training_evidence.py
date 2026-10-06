"""Hunter prerequisites cannot borrow another trainer or approximate learn evidence."""
import copy,struct
import pytest
from tools.client_compatibility.interaction_hunter_training import learned_checks
from tools.client_compatibility import interaction_pet_control_training as training


GUID=0xf130000000000000 | (46983<<32) | 280678


def evidence():
    rows=[{'direction':d,'name':n,'body':b.hex()} for d,n,b in (
        ('to_native','CMSG_TRAINER_BUY_SPELL',struct.pack('<QII',GUID,40,1515)),
        ('from_native','SMSG_LEARNED_SPELL',struct.pack('<II',1515,0)),
        ('to_client','SMSG_LEARNED_SPELLS',struct.pack('<IIBIB',1,0,0,1515,0)))]
    return rows,[],[[1515,1,0]],{'money':10000,'items':[6948]}, {'money':9354,'items':[6948]},[]


def check(data):
    rows,before_spells,after_spells,before,after,relation=data
    return learned_checks(rows,GUID,before_spells,after_spells,before,after,relation)


def test_exact_direct_hunter_lesson_native_client_and_persistence():
    assert all(check(evidence()).values())


@pytest.mark.parametrize('fault',['other_guid','other_trainer','warlock_spell','missing_delivery',
    'duplicate_purchase','duplicate_learn','wrong_cost','inventory_change','saved_child','dependent_relation','already_known'])
def test_hunter_training_refuses_borrowed_duplicate_or_incomplete_proof(fault):
    data=copy.deepcopy(evidence());rows,before_spells,after_spells,before,after,relation=data
    if fault=='other_guid':rows[0]['body']=struct.pack('<QII',GUID+1,40,1515).hex()
    elif fault=='other_trainer':rows[0]['body']=struct.pack('<QII',GUID,154,1515).hex()
    elif fault=='warlock_spell':rows[1]['body']=struct.pack('<II',93375,0).hex()
    elif fault=='missing_delivery':rows.pop()
    elif fault=='duplicate_purchase':rows.append(copy.deepcopy(rows[0]))
    elif fault=='duplicate_learn':rows.append(copy.deepcopy(rows[1]))
    elif fault=='wrong_cost':after['money']=9353
    elif fault=='inventory_change':after['items']=[]
    elif fault=='saved_child':after_spells[:]=[[93375,1,0]]
    elif fault=='dependent_relation':relation.append([1515,93375,1])
    else:before_spells.append([1515,1,0])
    assert not all(check(data).values())


def test_hunter_catalog_requires_its_native_entry_and_trainer(monkeypatch):
    packet={'session':'owned','time':10,'direction':'from_native','name':'SMSG_TRAINER_LIST',
        'body':struct.pack('<QIII',GUID,0,40,0).hex()}
    monkeypatch.setattr(training,'entries',lambda _: [packet])
    assert training.catalog('owned',9,entry=46983,trainer_id=40)['guid']==GUID
    with pytest.raises(RuntimeError,match='catalog absent'):training.catalog('owned',9)
    with pytest.raises(RuntimeError,match='catalog absent'):training.catalog('owned',9,entry=46983,trainer_id=154)
    with pytest.raises(RuntimeError,match='catalog absent'):training.catalog('foreign',9,entry=46983,trainer_id=40)
    with pytest.raises(RuntimeError,match='catalog absent'):training.catalog('owned',11,entry=46983,trainer_id=40)
