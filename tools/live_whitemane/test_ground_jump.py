import copy
from types import SimpleNamespace
import pytest
from . import ground_jump,sticky_input,camera_input,recovery,terrain_context,runtime,farm_graph
from .test_farm_loop import row


def ground():
    r=row();r['archaeology'].update(grounded=True,falling=False,swimming=False)
    r['movement'].update(sequence=0,facing_radians=0)
    r['owned_pose']={'height_yards':10};r['farm_ui']['frame_rate']=30
    return r


@pytest.mark.parametrize('flag',['mounted','flying','falling','swimming','casting'])
def test_grounded_jump_is_not_a_flight_or_water_command(flag):
    r=ground();assert ground_jump.legal(r)
    r['archaeology'][flag]=True;assert not ground_jump.legal(r)


@pytest.mark.parametrize('interrupted',[False,True])
def test_one_jump_uses_observed_landing_and_always_releases_inputs(monkeypatch,tmp_path,interrupted):
    (tmp_path/'run').mkdir();monkeypatch.setattr(runtime,'ROOT',tmp_path)
    before=ground();clock=[0.];events=[];controllers=[]
    sender=SimpleNamespace(X=SimpleNamespace(KeyPress='press',KeyRelease='release'),
        XK=SimpleNamespace(string_to_keysym=lambda x:x),_keycode=lambda x:(x,None),
        _send=lambda event,key:events.append((event,key)),close=lambda:events.append(('close',None)))
    monkeypatch.setattr(camera_input,'Input',lambda:sender)
    monkeypatch.setattr(ground_jump.inputs,'focus',lambda _: {})
    monkeypatch.setattr(ground_jump,'align',lambda *_ ,**__:[])
    monkeypatch.setattr(ground_jump.action_queue,'validate',lambda *_:None)
    monkeypatch.setattr(ground_jump.action_queue,'wait_stopped',lambda folder,row,observer:row)
    monkeypatch.setattr(ground_jump,'time',SimpleNamespace(time=lambda:clock[0],monotonic=lambda:clock[0],sleep=lambda s:None))
    def sticky(sender):
        control=sticky_input.StickyInput(sender,clock=lambda:clock[0],threaded=False)
        controllers.append(control);return control
    monkeypatch.setattr(ground_jump,'StickyInput',sticky)
    count=[0]
    def observe(_):
        count[0]+=1;clock[0]+=.1
        if controllers:controllers[0].tick()
        r=copy.deepcopy(before);r['movement']['sequence']=count[0]
        if count[0]==2:
            r['archaeology'].update(grounded=False,falling=True)
            r['owned_pose']['height_yards']=12
            r['archaeology']['world']['north']=1
        if count[0]>=3:
            r['archaeology']['world']['north']=3
            if interrupted:r['movement']['in_combat']=True
        return r
    monkeypatch.setattr(ground_jump,'observe',observe)
    target={'instance':1,'north':4,'west':0}
    if interrupted:
        with pytest.raises(RuntimeError,match='interrupted'):ground_jump.move(tmp_path,before,target)
    else:
        result=ground_jump.move(tmp_path,before,target)
        assert result['completed'] and result['outcome']=='landed'
        assert result['measured_jump_height_yards']==2 and result['forward_progress_yards']==3
    assert events.count(('press','space'))==events.count(('release','space'))==1
    assert events.count(('press','Up'))==events.count(('release','Up'))==1
    assert events[-1]==('close',None)


def test_blocked_portal_offers_a_jump_and_retains_the_portal_destination(monkeypatch,tmp_path):
    (tmp_path/'run').mkdir();monkeypatch.setattr(runtime,'ROOT',tmp_path)
    r=ground();target={'instance':1,'north':4,'west':0}
    graph=tmp_path/'graph.json';farm_graph.transition(graph,'portal',r,target=target)
    monkeypatch.setattr(recovery.escape_route,'candidates',lambda row,point:{
        'step_forward':{'target':target,'distance_yards':4,'reference_collision_clear':False}})
    monkeypatch.setattr(terrain_context,'facts',lambda *_:{'reference_climb_clear':True})
    monkeypatch.setattr(terrain_context,'detour',lambda *_:{'available':False})
    def choose(state,instructions,options):
        assert state['jump_forward_legal'] and 'jump_forward' in options
        return 'jump_forward',{},{}
    monkeypatch.setattr(recovery.laya_ui,'choose',choose)
    calls=[];monkeypatch.setattr(ground_jump,'move',lambda folder,row,point:calls.append(point) or {'completed':True})
    monkeypatch.setattr(recovery,'observe',lambda _:r)
    result=recovery.run(tmp_path/'recovery',r,{'phase':'portal','target':{'from':target},
        'local_failure':'continuous waypoint movement is blocked'},{'dig_output':None},graph)
    assert result['choice']=='jump_forward' and calls==[target]


@pytest.mark.parametrize('failure',['artifact tooltip observation did not follow the cursor',
    'no matching public tooltip in bounded interaction search','unexpected movement mode during continuous approach: swimming changed'])
def test_ui_search_failure_or_water_exit_does_not_offer_an_obstacle_jump(monkeypatch,tmp_path,failure):
    (tmp_path/'run').mkdir();monkeypatch.setattr(runtime,'ROOT',tmp_path)
    r=ground();target={'instance':1,'north':4,'west':0}
    graph=tmp_path/'graph.json';farm_graph.transition(graph,'portal',r,target=target)
    monkeypatch.setattr(recovery.escape_route,'candidates',lambda *_:{
        'step_forward':{'target':target,'distance_yards':4,'reference_collision_clear':False}})
    monkeypatch.setattr(terrain_context,'facts',lambda *_:{})
    monkeypatch.setattr(terrain_context,'detour',lambda *_:{'available':False})
    def choose(state,instructions,options):
        assert 'jump_forward' not in options and not state['forward_movement_blocked']
        return 'retry',{},{}
    monkeypatch.setattr(recovery.laya_ui,'choose',choose)
    monkeypatch.setattr(recovery,'observe',lambda _:r)
    monkeypatch.setattr(recovery.time,'sleep',lambda _:None)
    recovery.run(tmp_path/'recovery',r,{'phase':'portal','target':{'from':target},
        'local_failure':failure},{'dig_output':None},graph)
