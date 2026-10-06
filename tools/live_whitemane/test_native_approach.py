import copy
import pytest
from types import SimpleNamespace
from . import interact,portal,taxi,farm_policy,dig_decisions,runtime
from .dig_policy import SolveBatches
from .test_farm_loop import row


def named(name):
    r=row();r['archaeology'].update(falling=False,swimming=False)
    r['farm_ui'].update(tooltip=name,cursor={'x':.5,'y':.5},sequence=1,
        combat={'click_to_move':'1'},camera_input={'right_down':False,'mouselooking':False})
    return r


@pytest.mark.parametrize('change',['wrong_name','disabled','camera','flying','swimming','combat'])
def test_native_approach_requires_fresh_named_ground_mouseover_and_enabled_client_movement(change):
    r=named('Doras')
    assert interact.native_approach_available(r,{'Doras'})
    if change=='wrong_name':r['farm_ui']['tooltip']='Unrelated'
    elif change=='disabled':r['farm_ui']['combat']['click_to_move']='0'
    elif change=='camera':r['farm_ui']['camera_input']['right_down']=True
    elif change=='combat':r['movement']['in_combat']=True
    else:r['archaeology'][change]=True
    assert not interact.native_approach_available(r,{'Doras'})


def test_distant_named_portal_and_flight_master_are_legal_without_coordinate_approach():
    r=named('Portal to Orgrimmar')
    p={'key':'tb-org','destination':'Orgrimmar','from':{'instance':1,'north':45,'west':0}}
    r['farm_ui']['route']={'kind':'portal','portal':p,'known_portals':[]}
    assert farm_policy.legal_actions(r,SolveBatches())['portal'][1]==p
    r['farm_ui']['tooltip']='Doras'
    origin={'id':23,'point':p['from']};destination={'id':531,'point':{'instance':1,'north':200,'west':0}}
    r['farm_ui']['route']={'kind':'taxi','origin':origin,'exit':destination}
    assert farm_policy.legal_actions(r,SolveBatches())['taxi'][1]==(origin,destination)
    r['farm_ui']['combat']['click_to_move']='0'
    assert 'taxi' not in farm_policy.legal_actions(r,SolveBatches())


def test_artifact_native_approach_remains_a_choice_alongside_mouse_button_five(monkeypatch):
    state={'available':True,'casting':False,'artifact_visible':True,
        'mouseover_artifact':'Troll Archaeology Find','native_artifact_approach_available':True}
    def choose(state,instructions,options):
        assert 'right_click_approach' in options and 'mouseover_interact' in options
        return 'right_click_approach',{},{}
    monkeypatch.setattr(dig_decisions.laya_ui,'choose',choose)
    assert dig_decisions.choose(state)[0]=='right_click_approach'


def test_distant_portal_uses_one_named_click_then_waits_for_client_arrival(monkeypatch,tmp_path):
    monkeypatch.setattr(runtime,'ROOT',tmp_path);(tmp_path/'run').mkdir()
    before=named('Portal to Orgrimmar')
    p={'key':'tb-org','destination':'Orgrimmar','from':{'instance':1,'north':45,'west':0},
        'to':{'instance':1,'north':200,'west':0}}
    now=[0];clicks=[];frames=[0]
    monkeypatch.setattr(portal,'time',SimpleNamespace(monotonic=lambda:now[0],sleep=lambda s:now.__setitem__(0,now[0]+s)))
    def observe(path):
        frames[0]+=1;r=copy.deepcopy(before)
        if frames[0]>2:r['archaeology']['world']['north']=200 if now[0]>=6 else now[0]*7
        return r
    monkeypatch.setattr(portal,'observe',observe)
    monkeypatch.setattr(portal,'stationary',lambda *_:None)
    monkeypatch.setattr(portal,'walk',lambda *_ ,**kw:pytest.fail('native click should own movement'))
    monkeypatch.setattr(portal,'align',lambda *_ ,**kw:pytest.fail('named mouseover needs no camera reset'))
    def use(folder,row,names,**kwargs):
        assert kwargs=={'maximum':1,'native_right_click':True}
        clicks.append(names);return {'name':'Portal to Orgrimmar','native_approach':True}
    monkeypatch.setattr(interact,'use',use)
    result=portal.run(tmp_path/'portal',p,approved_intent=('portal','model',{},{}))
    assert result['completed'] and len(clicks)==1 and now[0]>=6
    assert result['approach']['client_owns_approach_and_interaction']


def test_flight_master_approach_waits_beyond_two_seconds_for_menu(monkeypatch,tmp_path):
    before=named('Doras');now=[0]
    monkeypatch.setattr(taxi,'time',SimpleNamespace(monotonic=lambda:now[0],sleep=lambda s:now.__setitem__(0,now[0]+s)))
    def observe(_):
        r=copy.deepcopy(before);r['archaeology']['world']['north']=min(42,now[0]*7)
        if now[0]>=6:r['farm_ui']['taxi']=[{'id':531}]
        return r
    monkeypatch.setattr(taxi,'observe',observe)
    after=taxi.wait_menu(tmp_path,before,native_target={'instance':1,'north':42,'west':0})
    assert after['farm_ui']['taxi'] and 6<=now[0]<6.1


def test_near_range_refusal_yields_to_movement_and_suppresses_same_click_shortcut(monkeypatch,tmp_path):
    from . import native_approach
    monkeypatch.setattr(runtime,'ROOT',tmp_path)
    before=named('Troll Archaeology Find');before['movement']['sequence']=1
    before['farm_ui']['uptime']=10
    first=copy.deepcopy(before);first['movement']['sequence']=2
    first['farm_ui']['error']={'message':'Out of range.','at':10.05}
    second=copy.deepcopy(first);second['movement']['sequence']=3
    feedback=native_approach.Feedback(before)
    assert not feedback.refused(first)
    assert not feedback.refused(first), 'repeated stale frames do not confirm no movement'
    assert feedback.refused(second)
    assert not interact.native_approach_available(second,{'Troll Archaeology Find'})
    moved=copy.deepcopy(second);moved['archaeology']['world']['north']=2
    assert interact.native_approach_available(moved,{'Troll Archaeology Find'})
    collected=copy.deepcopy(second);collected['archaeology']['looted_finds']=1
    assert interact.native_approach_available(collected,{'Troll Archaeology Find'})


def test_range_refusal_does_not_cancel_an_actual_native_approach_or_cast(monkeypatch,tmp_path):
    from . import native_approach
    monkeypatch.setattr(runtime,'ROOT',tmp_path)
    before=named('Doras');before['movement']['sequence']=1;before['farm_ui']['uptime']=10
    feedback=native_approach.Feedback(before)
    for index in range(2,5):
        fresh=copy.deepcopy(before);fresh['movement'].update(sequence=index,speed=7)
        fresh['archaeology']['world']['north']=index
        fresh['farm_ui']['error']={'message':'Out of range.','at':10.05}
        assert not feedback.refused(fresh)
    fresh['movement'].update(sequence=5,speed=0);fresh['archaeology']['casting']=True
    assert not feedback.refused(fresh)
    assert not (tmp_path/'run/native_approach_refusal.json').exists()


def test_near_artifact_range_error_requires_a_closer_guide_than_half_a_yard():
    from . import guide
    r=named('Troll Archaeology Find');r['movement']['facing_radians']=0
    r['visible_find']={'world':{'instance':1,'north':.3,'west':0}}
    session={'reapproach_find':True,'pending_find':{'out_of_range':True}}
    result,_=guide.select(r,session,None)
    assert not result['arrived'] and result['arrival_tolerance_yards']==.1


@pytest.mark.parametrize('name',['Portal to Orgrimmar','Doras','Troll Archaeology Find'])
def test_native_object_click_releases_right_button_and_never_uses_mouse_five(monkeypatch,tmp_path,name):
    from tools.client_compatibility import native_input_adapter
    from . import laya_ui
    monkeypatch.setattr(runtime,'ROOT',tmp_path);(tmp_path/'run').mkdir()
    before=named(name);before['farm_ui']['uptime']=10
    frames=[]
    for sequence in (2,3):
        fresh=copy.deepcopy(before);fresh['farm_ui']['sequence']=sequence;frames.append(fresh)
    frames=iter(frames);monkeypatch.setattr(interact,'observe',lambda _:next(frames))
    monkeypatch.setattr(interact.inputs,'focus',lambda _:{'owned':True})
    events=[]
    sender=SimpleNamespace(X=SimpleNamespace(ButtonPress='down',ButtonRelease='up'),
        initialization={'owned':True},move=lambda *p:events.append(('move',p)),
        _send=lambda *p:events.append(p),close=lambda:events.append(('close',)))
    monkeypatch.setattr(native_input_adapter,'Input',lambda:sender)
    monkeypatch.setattr(interact.time,'sleep',lambda _:None)
    def choose(state,instructions,options):
        assert state['client_click_to_move'] and 'right_click' in options
        assert 'mouseover_interact' not in options
        return 'right_click',{},{}
    monkeypatch.setattr(laya_ui,'choose',choose)
    result=interact.use(tmp_path/'search',before,{name},maximum=1,native_right_click=True)
    assert result['native_approach'] and result['client_uptime_at_click']==10
    assert events==[('move',(640,450)),('move',(640,450)),('down',3),('up',3),('close',)]
