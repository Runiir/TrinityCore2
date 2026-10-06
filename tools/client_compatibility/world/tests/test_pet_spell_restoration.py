"""No pet-reset input without fresh matching owned native/public control and summon eligibility."""
import copy,json
from pathlib import Path
from types import SimpleNamespace
import pytest
from tools.client_compatibility import interaction_pet_spell as run
from tools.client_compatibility.world.objects import INDEX

FIXTURE=json.loads((Path(__file__).parent/'fixtures/native_trained_pet_manual_spell_ui131.json').read_text())


def setup(monkeypatch):
    pet=copy.deepcopy(FIXTURE['native_pet_create']);pet['fields']={int(k):v for k,v in pet['fields'].items()}
    public=copy.deepcopy(FIXTURE['baseline_public_probe']);sample={'probe':public,'ui_clean':True}
    o=SimpleNamespace(pet=pet,session='s',present=lambda:True,poll=lambda:None)
    t=SimpleNamespace(fixture={'guid':5})
    monkeypatch.setattr(run,'read',lambda *_:sample);monkeypatch.setattr(run,'wire_known',lambda *_:{688})
    return t,o,sample


def test_actual_unchanged_owned_public_probe_and_native_pet_allow_cleanup_authority(monkeypatch):
    t,o,sample=setup(monkeypatch);assert run.cleanup_authority(t,o) is sample


def test_disabled_spell_authority_is_only_accepted_when_reset_explicitly_expects_disabled(monkeypatch):
    t,o,sample=setup(monkeypatch)
    next(r for r in sample['probe']['actions'] if r.get('spell_id')==6307)['autocast_enabled']=False
    assert run.cleanup_authority(t,o,enabled=False) is sample
    with pytest.raises(RuntimeError):run.cleanup_authority(t,o)


def test_enabled_spell_cannot_claim_disabled_cleanup_authority(monkeypatch):
    t,o,_=setup(monkeypatch)
    with pytest.raises(RuntimeError):run.cleanup_authority(t,o,enabled=False)


@pytest.mark.parametrize('fault',['actor','ui_error','lost_pet','foreign_kind','foreign_owner','wrong_number',
    'unknown_summon','public_owner','public_pet','disabled_spell','missing_button','invisible_button','unavailable_button'])
def test_reset_refuses_before_any_gameplay_input_with_stale_or_unowned_cleanup_authority(monkeypatch,fault):
    t,o,sample=setup(monkeypatch);inputs=[];t.execute=lambda action:inputs.append(action)
    if fault=='actor':t.fixture['guid']=4
    elif fault=='ui_error':sample['ui_clean']=False
    elif fault=='lost_pet':o.present=lambda:False
    elif fault=='foreign_kind':o.pet['kind']=4
    elif fault=='foreign_owner':o.pet['fields'][INDEX['UNIT_FIELD_SUMMONEDBY']]=6
    elif fault=='wrong_number':o.pet['fields'][INDEX['UNIT_FIELD_PETNUMBER']]=1
    elif fault=='unknown_summon':monkeypatch.setattr(run,'wire_known',lambda *_:set())
    elif fault=='public_owner':sample['probe']['owner_guid']='Player-1-00000004'
    elif fault=='public_pet':sample['probe']['pet_guid']='Pet-0-1-0-0-416-00000000FF'
    else:
        row=next(r for r in sample['probe']['actions'] if r.get('spell_id')==6307)
        if fault=='disabled_spell':row['autocast_enabled']=False
        elif fault=='missing_button':sample['probe']['actions'].remove(row)
        elif fault=='invisible_button':row['frame']['visible']=False
        else:row['frame']['available']=False
    with pytest.raises(RuntimeError):run.reset_pet(t,o)
    assert inputs==[]
