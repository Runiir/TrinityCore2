import sys
import types
from . import controller_updates


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
