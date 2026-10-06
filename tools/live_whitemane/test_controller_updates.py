import sys
import types
from . import controller_updates


def test_queue_signature_changes_reload_their_camera_and_movement_consumers(monkeypatch,tmp_path):
    names=('action_queue','camera_navigation','fast_waypoint')
    assert all(name in controller_updates.COMPONENTS for name in names)
    modules={}
    for name,source in zip(names,('def wait_stopped():pass\n',
            'def align():\n from .action_queue import wait_stopped\n',
            'def walk():\n from .action_queue import wait_stopped\n')):
        path=tmp_path/(name+'.py');path.write_text(source)
        module=types.ModuleType(controller_updates.__package__+'.'+name);module.__file__=str(path)
        modules[name]=module;monkeypatch.setitem(sys.modules,module.__name__,module)
    monkeypatch.setattr(controller_updates,'COMPONENTS',names)
    monkeypatch.setattr(controller_updates.runtime,'ROOT',tmp_path)
    calls=[];monkeypatch.setattr(controller_updates.importlib,'reload',lambda m:calls.append(m.__name__))
    updates=controller_updates.SourceUpdates()
    (tmp_path/'action_queue.py').write_text('def wait_stopped(*,camera_released=False):pass\n')
    assert updates.refresh()==[]
    assert updates.refresh()==list(names)
    assert calls==[modules[name].__name__ for name in names]


def test_source_updates_load_between_actions_and_refresh_dependent_function_aliases(monkeypatch,tmp_path):
    names=('test_leaf','test_consumer');modules={}
    for name,source in zip(names,('value=1\n','from .test_leaf import value\n')):
        path=tmp_path/(name+'.py');path.write_text(source)
        module=types.ModuleType(controller_updates.__package__+'.'+name);module.__file__=str(path)
        modules[name]=module;monkeypatch.setitem(sys.modules,module.__name__,module)
    monkeypatch.setattr(controller_updates,'COMPONENTS',names)
    monkeypatch.setattr(controller_updates.runtime,'ROOT',tmp_path)
    calls=[];monkeypatch.setattr(controller_updates.importlib,'reload',lambda m:calls.append(m.__name__))
    updates=controller_updates.SourceUpdates()
    leaf=tmp_path/'test_leaf.py';leaf.write_text('value=2\n')
    assert updates.refresh()==[] and not calls
    assert updates.refresh()==list(names)
    assert calls==[modules[name].__name__ for name in names]
    leaf.write_text('value=\n')
    assert updates.refresh()==updates.refresh()==[] and len(calls)==2
    leaf.write_text('value=3\n')
    assert updates.refresh()==[]
    assert updates.refresh()==list(names)


def test_addon_reload_waits_for_combat_to_end_and_does_not_interrupt_a_pending_find(monkeypatch,tmp_path):
    from .test_farm_loop import row
    import json
    monkeypatch.setattr(controller_updates.runtime,'ROOT',tmp_path)
    (tmp_path/'run').mkdir()
    path=tmp_path/'run/addon_reload_request.json';path.write_text(json.dumps({'receipt':str(tmp_path/'receipt.json')}))
    r=row();r['movement']['in_combat']=True
    monkeypatch.setattr(controller_updates.pending_find,'load',lambda _:None)
    assert not controller_updates.apply_addon_request(tmp_path,r) and path.exists()
    r['movement']['in_combat']=False
    monkeypatch.setattr(controller_updates.pending_find,'load',lambda _:{'site_id':169})
    assert not controller_updates.apply_addon_request(tmp_path,r) and path.exists()
    r['farm_ui']['combat_facts_schema']='observed_attackers_v1'
    assert not controller_updates.apply_addon_request(tmp_path,r) and not path.exists()


def test_reload_expected_facts_support_mixed_nested_and_flat_fields():
    expected={'combat_facts_schema':'observed_attackers_v1',
        'route':{'route_facts_schema':'instant_fare_routes_v1'},
        'terrain_environment':{'schema':'public_environment_v1','indoors':False}}
    assert controller_updates.matches_expected(expected,expected)
    assert not controller_updates.matches_expected({'combat_facts_schema':'observed_attackers_v1'},expected)
    incomplete={**expected,'terrain_environment':{'schema':'public_environment_v1'}}
    assert not controller_updates.matches_expected(incomplete,expected)


def test_startup_reload_callback_is_updated_even_after_multiple_module_reloads(monkeypatch):
    old=types.FunctionType((lambda folder,row:False).__code__,controller_updates.__dict__)
    old.__module__=controller_updates.__name__
    frame=types.SimpleNamespace(f_globals={'__name__':'__main__'},
        f_code=types.SimpleNamespace(co_name='run',co_filename=str(controller_updates.runtime.REPO/'tools/live_whitemane/farm_loop.py')),
        f_locals={'apply_addon_request':old},f_back=None)
    monkeypatch.setattr(controller_updates.sys,'_current_frames',lambda:{1:frame})
    assert controller_updates.upgrade_bound_callbacks()==1
    assert old.__code__ is controller_updates.apply_addon_request.__code__


def test_ui_setup_advances_live_index_and_runs_evidence_cleanup_without_restart(monkeypatch,tmp_path):
    from . import camera_recovery,resources
    from .test_farm_loop import row
    session={'next_step_index':4,'dig_output':'active dig','steps':[]}
    frame=types.SimpleNamespace(f_code=types.SimpleNamespace(co_name='run',
        co_filename=str(controller_updates.runtime.REPO/'tools/live_whitemane/farm_loop.py')),
        f_locals={'session':session},f_back=None)
    wrapper=types.SimpleNamespace(f_code=types.SimpleNamespace(co_name='apply_addon_request',
        co_filename=controller_updates.__file__),f_back=frame)
    monkeypatch.setattr(controller_updates.sys,'_getframe',lambda _:wrapper)
    monkeypatch.setattr(camera_recovery,'apply_request',lambda *_:True)
    calls=[];monkeypatch.setattr(resources,'phase_boundary',lambda output,state:calls.append((output,state.copy())))
    assert controller_updates.apply_camera_request(tmp_path/'step_00009',row())
    assert session['next_step_index']==10 and session['steps']==[]
    assert calls[0][0]==tmp_path and calls[0][1]['dig_output']=='active dig'
