import copy
import json
from . import farm_graph,observed_state,runtime
from .test_farm_loop import row


def test_manual_teleport_changes_graph_state_without_an_action_record(tmp_path):
    r=row();r.update(observed_at=1)
    r['archaeology'].update(can_survey=True,loot_open=False,falling=False)
    path=tmp_path/'graph.json'
    farm_graph.transition(path,'survey',r)
    before=json.loads(path.read_text());assert before['current']=='dig'
    r['movement']['map_id']=245;r['archaeology'].update(can_survey=False,
        world={'instance':732,'north':-601.4,'west':1382.0})
    r['farm_ui']['route']['portal']={'from':{'instance':732,'north':-599.2,'west':1378.4}}
    changed=farm_graph.refresh(path,r)
    assert changed['current']=='travel' and changed['facts']['map_id']==245
    assert changed['transition_conditions']['use_portal'] is True
    assert changed['last_action_node']=='survey' and changed['events']==before['events']
    r['movement']['in_combat']=True
    r['archaeology'].update(mounted=True,flying=True)
    changed=farm_graph.refresh(path,r)
    assert changed['current']=='combat' and changed['facts']['mounted'] is True
    assert changed['facts']['flying'] is True and changed['events']==before['events']


def test_observation_publisher_updates_state_while_laya_does_nothing(monkeypatch,tmp_path):
    from . import laya_ui
    monkeypatch.setattr(runtime,'ROOT',tmp_path)
    monkeypatch.setattr(laya_ui,'choose',lambda *_:(_ for _ in ()).throw(AssertionError('must not call Laya')))
    r=row();r.update(observed_at=1,source='public_test')
    frames=iter([copy.deepcopy(r),r])
    r['movement']['in_combat']=True;r['archaeology']['mounted']=True;r['observed_at']=2
    monkeypatch.setattr(observed_state,'observe',lambda _:next(frames))
    assert observed_state.sample()['facts']['combat'] is False
    assert observed_state.sample()['facts']['combat'] is True
    saved=json.loads((tmp_path/'run/world_state.json').read_text())
    assert saved['facts']['mounted'] is True and saved['action_dependency'] is False
