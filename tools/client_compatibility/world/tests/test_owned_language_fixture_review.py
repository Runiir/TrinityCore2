import json
from types import SimpleNamespace
import pytest
from tools.client_compatibility import interaction_owned_language_fixture as fixture


@pytest.mark.parametrize('change',[None,'source','image','monitor','actor','game_lifetime'])
def test_owned_lobby_review_rejects_unbound_evidence(tmp_path,monkeypatch,change):
    monkeypatch.setattr(fixture.lab,'ROOT',tmp_path)
    monkeypatch.setattr(fixture.lab,'owned_process',lambda kind:{'pid':99})
    monkeypatch.setattr(fixture.owned_input,'focus',lambda:{'input_isolation':{'game_pid':101}})
    p=tmp_path/'evidence';p.mkdir();image=p/'review.png';image.write_bytes(b'owned retained frame')
    d={'fixture_source_sha256':'a'*64,'frame':{'file':image.name,'sha256':fixture.lab.sha256(image),
        'monitor':{'second_monitor_verified':True,'pid':99,'input_isolation':{'actor':'scout','game_pid':101}}}}
    if change=='source':d['fixture_source_sha256']='b'*64
    elif change=='image':image.write_bytes(b'changed frame')
    elif change=='monitor':d['frame']['monitor']['second_monitor_verified']=False
    elif change=='actor':d['frame']['monitor']['input_isolation']['actor']='primary'
    elif change=='game_lifetime':d['frame']['monitor']['input_isolation']['game_pid']=102
    path=p/'review.json';path.write_text(json.dumps(d))
    t=SimpleNamespace(receipt={'fixture_source':{'sha256':'a'*64}},persist=lambda:None)
    if change is None:
        fixture.reviewed(t,path);assert t.receipt['reviewed_lobby']['frame']==d['frame']
    else:
        with pytest.raises(RuntimeError,match='reviewed owned lobby frame differs'):fixture.reviewed(t,path)


@pytest.mark.parametrize('change',[None,'open','completed','actor','source','online','entered','skills'])
def test_rejected_entry_cleanup_requires_offline_unchanged_owned_actors(tmp_path,monkeypatch,change):
    root=tmp_path/'evidence';root.mkdir();monkeypatch.setattr(fixture.lab,'ROOT',tmp_path)
    source=root/'prepare'/'episode.json';source.parent.mkdir();source.write_text('{}')
    actor={'guid':3,'account_id':2};origin={'guid':2,'account_id':2}
    runtime={'client':{'pid':99,'start_ticks':'1'}}
    old={'started_at':1,'origin_actor':origin,'origin_baseline':{'spells':[],'skills':[[98,300,300]],'actions':[]},
        'natural_rows':{'spells':[],'skills':[[111,300,300]]}}
    failed={'completed':False,'finished_at':2,'failure':'login rejected','actor':actor,'runtime':runtime,
        'fixture_source':{'sha256':fixture.lab.sha256(source)}}
    if change=='open':failed['finished_at']=None
    elif change=='completed':failed['completed']=True
    elif change=='actor':failed['actor']=origin
    elif change=='source':failed['fixture_source']['sha256']='bad'
    path=root/'enter'/'episode.json';path.parent.mkdir();path.write_text(json.dumps(failed))
    monkeypatch.setattr(fixture,'prepared',lambda *a:old)
    monkeypatch.setattr(fixture,'entries',lambda p:iter([{'time':1.5,'event':'native_player_created','guid':3}]
        if change=='entered' else []))
    class Context:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def cursor(self):return self
        def execute(self,*a):pass
        def fetchall(self):return ((2,0),(3,1 if change=='online' else 0))
    monkeypatch.setattr(fixture.lab,'connection',Context)
    monkeypatch.setattr(fixture,'known',lambda g:[])
    monkeypatch.setattr(fixture,'skills',lambda g:[[98,1,300]] if change=='skills' and g==2 else
        ([[98,300,300]] if g==2 else [[111,300,300]]))
    monkeypatch.setattr(fixture,'saved_actions',lambda g:[])
    registered=[]
    monkeypatch.setattr(fixture.actors,'register',lambda g:registered.append(g) or origin)
    monkeypatch.setattr(fixture,'shot',lambda p:{'file':p.name})
    t=SimpleNamespace(fixture=actor,receipt={'runtime':runtime},persist=lambda:None,out=root)
    if change is None:
        fixture.rejected_entry(t,source,path)
        assert registered==[2] and t.receipt['phase']=='await_owned_origin_selection'
    else:
        with pytest.raises(RuntimeError):fixture.rejected_entry(t,source,path)
        assert registered==[]
