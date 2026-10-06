"""A parked class resumes only after the exact unchanged restoration chain."""
import copy
from types import SimpleNamespace
import pytest
from tools.client_compatibility import interaction_retained_class_reentry as module


def chain():
    origin={'guid':2,'account_id':2};fixture={'guid':4,'account_id':2}
    runtime={'worldserver':{'pid':1},'modern_world':{'pid':2},'client':{'pid':3}}
    old={'phase':'await_owned_class_lobby_review','origin_actor':origin,'class_actor':fixture,
        'actor':origin,'runtime':copy.deepcopy(runtime),'finished_at':1}
    checks=dict.fromkeys(('original_character','original_saved_rows','native_worldserver','class_offline'),True)
    park={'actor':fixture,'runtime':copy.deepcopy(runtime),'phase':'await_original_selection_review',
        'fixture_source':{'sha256':'source'},'checks':checks,'started_at':2,'finished_at':3}
    finish={'actor':origin,'runtime':copy.deepcopy(runtime),'fixture_source':{'sha256':'source'},
        'checks':{**checks,'origin_registration':True},'started_at':4,'finished_at':5}
    return SimpleNamespace(fixture=origin,receipt={'runtime':runtime}),old,park,finish


def test_exact_unchanged_chain_accepts_retained_fixture():
    module.continuity(*chain(),'source')


@pytest.mark.parametrize('change',['none','name','race','class','level','account','guid'])
def test_separate_eligible_fixture_requires_its_exact_owned_identity(change):
    t,old,park,finish=chain()
    fixture={'guid':5,'account_id':2,'character_name':'Harnessctrl','race':1,'class':9,'level':10}
    if change!='none':
        key={'name':'character_name','account':'account_id'}.get(change,change)
        fixture[key]='Harnessone' if key=='character_name' else 99
    old['class_actor']=fixture;park['actor']=fixture
    if change=='none':module.continuity(t,old,park,finish,'source')
    else:
        with pytest.raises(RuntimeError):module.continuity(t,old,park,finish,'source')


@pytest.mark.parametrize('change',('class','origin','actor','park_actor','finish_actor','bridge','server','client',
    'park_source','finish_source','park_phase','park_false','finish_missing','renamed_check','overlap','unfinished_order'))
def test_changed_actor_lifetime_source_or_restoration_refuses_reentry(change):
    t,old,park,finish=chain()
    if change=='class':old['class_actor']['guid']=5
    elif change=='origin':old['origin_actor']={**old['origin_actor'],'guid':3}
    elif change=='actor':old['actor']={'guid':3}
    elif change=='park_actor':park['actor']={'guid':3}
    elif change=='finish_actor':finish['actor']={'guid':3}
    elif change in ('bridge','server','client'):
        key={'bridge':'modern_world','server':'worldserver','client':'client'}[change];t.receipt['runtime'][key]['pid']=9
    elif change=='park_source':park['fixture_source']['sha256']='wrong'
    elif change=='finish_source':finish['fixture_source']['sha256']='wrong'
    elif change=='park_phase':park['phase']='unfinished'
    elif change=='park_false':park['checks']['class_offline']=False
    elif change=='finish_missing':finish['checks'].pop('origin_registration')
    elif change=='renamed_check':park['checks']['unrelated']=park['checks'].pop('class_offline')
    elif change=='overlap':finish['started_at']=2.5
    else:park['finished_at']=1
    with pytest.raises(RuntimeError):module.continuity(t,old,park,finish,'source')


@pytest.mark.parametrize('change',('none','character','saved','pets','registration'))
def test_exact_current_rows_are_checked_before_registration(tmp_path,monkeypatch,change):
    t,old,park,finish=chain();t.persist=lambda:None;t.out=tmp_path
    old.update(origin_native={'guid':2},origin_saved={},origin_roster=[])
    park.update(retained_class_fixture={'guid':4,'online':0},retained_class_saved={'spells':[688]},
        retained_class_pets=[{'id':1,'owner':4}])
    sources=[tmp_path/n/'episode.json' for n in ('preparation','park','finish')]
    monkeypatch.setattr(module,'closed',lambda p:dict(zip(sources,(old,park,finish)))[p])
    monkeypatch.setattr(module.lab,'sha256',lambda p:'source')
    monkeypatch.setattr(module,'origin_checks',lambda d:dict.fromkeys(('original_character','original_saved_rows','native_worldserver'),True))
    monkeypatch.setattr(module,'character',lambda *a:{'guid':4,'online':1 if change=='character' else 0})
    monkeypatch.setattr(module,'saved',lambda *a:{'spells':[] if change=='saved' else [688]})
    monkeypatch.setattr(module,'pets',lambda *a:[] if change=='pets' else [{'id':1,'owner':4}])
    monkeypatch.setattr(module.actors,'load',lambda:{'guid':3} if change=='registration' else t.fixture)
    calls=[]
    def register(guid):calls.append(guid);return old['class_actor']
    monkeypatch.setattr(module.actors,'register',register)
    monkeypatch.setattr(module,'shot',lambda p:{'file':p.name})
    if change=='none':
        module.prepare(t,*sources);assert calls==[4] and t.receipt['completed'] is True
    else:
        with pytest.raises(RuntimeError):module.prepare(t,*sources)
        assert calls==[]


@pytest.mark.parametrize('change',('none','wrong_version','copy_mismatch'))
def test_offline_observer_installation_binds_every_committed_file(tmp_path,monkeypatch,change):
    source=tmp_path/'tools/client_compatibility/observation/addon/ClientMovementHarness'
    target=tmp_path/'client/_whitemane-60895_/Interface/AddOns/ClientMovementHarness'
    source.mkdir(parents=True);target.mkdir(parents=True)
    (source/'ClientInteractions.lua').write_text('observer_version=129')
    (source/'SpellBookObservation.lua').write_text('passive pet power reading')
    (target/'ClientInteractions.lua').write_text('observer_version=128')
    monkeypatch.setattr(module.lab,'REPO',tmp_path)
    monkeypatch.setattr(module.lab,'client_root',lambda:tmp_path)
    if change=='copy_mismatch':monkeypatch.setattr(module.shutil,'copytree',lambda *a,**kw:None)
    t=SimpleNamespace(receipt={},persist=lambda:None)
    if change=='none':
        module.install_observer(t,129);record=t.receipt['parked_observer_installation']
        assert record['source']==record['after'] and record['before']!=record['after']
        assert record['input_sent'] is False and record['version']==129
    else:
        with pytest.raises(RuntimeError):module.install_observer(t,128 if change=='wrong_version' else 129)
        assert not t.receipt and (target/'ClientInteractions.lua').read_text()=='observer_version=128'
