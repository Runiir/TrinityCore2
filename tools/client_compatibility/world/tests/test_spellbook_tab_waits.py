"""Delayed stock tab changes must be observed without another game input."""
from contextlib import nullcontext
from types import SimpleNamespace
import pytest
from tools.client_compatibility import interaction_observation as observation
from tools.client_compatibility import interaction_spellbook_navigation as navigation


def fixture(monkeypatch,tmp_path,books):
    samples=iter({'guid':'owned','observer_version':62,'sequence':i,'mode':'spellbook',
                  'spellbook_probe':{'book_type':book}} for i,book in enumerate(books))
    captures=[]
    def shot(path):
        captures.append(path)
        return {'file':path.name}
    monkeypatch.setattr(observation,'shot',shot)
    monkeypatch.setattr(observation.Image,'open',lambda _:nullcontext(next(samples)))
    monkeypatch.setattr(observation,'decode_image',lambda state:state)
    monkeypatch.setattr(observation.time,'sleep',lambda _:None)
    t=SimpleNamespace(out=tmp_path,guid='owned',receipt={},persist=lambda:None)
    return t,captures


def test_profession_read_waits_past_old_spellbook_frames(monkeypatch,tmp_path):
    t,captures=fixture(monkeypatch,tmp_path,['spell','spell','professions'])
    assert navigation.detail(t,'profession',book_type='professions')['book_type']=='professions'
    assert len(captures)==3
    wait=t.receipt['observation_settling'][0]
    assert len(wait['samples'])==2 and wait['input_replayed'] is False


def test_restoration_waits_past_old_profession_frame(monkeypatch,tmp_path):
    t,captures=fixture(monkeypatch,tmp_path,['professions','spell'])
    assert navigation.detail(t,'restore',book_type='spell')['book_type']=='spell'
    assert len(captures)==2


def test_tab_timeout_fails_without_qualifying_stale_page(monkeypatch,tmp_path):
    t,captures=fixture(monkeypatch,tmp_path,['spell'])
    # Simulate a pause beyond the diagnostic reader's current 28-second budget.
    ticks=iter([0,60])
    monkeypatch.setattr(observation.time,'monotonic',lambda:next(ticks))
    with pytest.raises(RuntimeError,match='spellbook diagnostic did not become visible'):
        navigation.detail(t,'profession',book_type='professions')
    assert len(captures)==1 and not t.receipt.get('spellbook_details')


def test_class_and_page_reads_wait_for_the_requested_native_book_location(monkeypatch,tmp_path):
    samples=iter([{'book_type':'spell','skill_line':1,'page':1},
                  {'book_type':'spell','skill_line':3,'page':1},
                  {'book_type':'spell','skill_line':3,'page':2}])
    t,_=fixture(monkeypatch,tmp_path,[])
    sequence=iter(range(3))
    monkeypatch.setattr(observation.Image,'open',lambda _:nullcontext({
        'guid':'owned','observer_version':63,'sequence':next(sequence),'mode':'spellbook',
        'spellbook_probe':next(samples)}))
    probe=navigation.detail(t,'class_page',book_type='spell',line=3,page=2)
    assert (probe['skill_line'],probe['page'])==(3,2)
    assert len(t.receipt['observation_settling'][0]['samples'])==2
