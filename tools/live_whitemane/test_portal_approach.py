import copy
import pytest
from . import portal
from .test_farm_loop import row


def test_portal_retains_its_selected_movement_intent_and_confirms_arrival(monkeypatch,tmp_path):
    before=row();before['archaeology']['falling']=False
    entrance={'instance':1,'north':21,'west':0}
    destination={'instance':732,'north':-601,'west':1382}
    after=copy.deepcopy(before);after['archaeology']['world']=destination
    frames=iter([before,before,before,before,after])
    monkeypatch.setattr(portal,'observe',lambda _:next(frames))
    monkeypatch.setattr(portal,'stationary',lambda *_:None)
    monkeypatch.setattr(portal.action_queue,'wait_stopped',lambda folder,row,observer:row)
    monkeypatch.setattr(portal,'align',lambda folder,row,target,**kwargs:[{'view_reset':kwargs['reset_view']}])
    monkeypatch.setattr(portal,'choose',lambda *_,**kwargs:('portal',{}, {}, {}))
    walks=[]
    def walk(folder,target,**kwargs):
        walks.append(target)
        assert kwargs['approved_intent'][0]=='portal' and kwargs['tolerance']==.4
        return []
    monkeypatch.setattr(portal,'walk',walk)
    monkeypatch.setattr(portal.interact,'use',lambda *_:{'completed':True})
    monkeypatch.setattr(portal.time,'sleep',lambda _:None)
    result=portal.run(tmp_path/'portal',{'from':entrance,'to':destination,'destination':'Tol Barad'})
    assert result['completed'] and walks==[entrance]
    assert 'turn_input' not in result


def test_selected_portal_intent_is_not_replaced_by_a_second_model_choice(monkeypatch,tmp_path):
    before=row();before['archaeology']['falling']=False
    entrance={'instance':1,'north':21,'west':0};destination={'instance':732,'north':-601,'west':1382}
    after=copy.deepcopy(before);after['archaeology']['world']=destination
    frames=iter([before,before,before,before,after])
    monkeypatch.setattr(portal,'observe',lambda _:next(frames))
    monkeypatch.setattr(portal,'stationary',lambda *_:None)
    monkeypatch.setattr(portal.action_queue,'wait_stopped',lambda folder,row,observer:row)
    monkeypatch.setattr(portal,'align',lambda folder,row,target,**kwargs:[{'view_reset':kwargs['reset_view']}])
    monkeypatch.setattr(portal,'choose',lambda *_,**__:pytest.fail('do not replace selected intent'))
    intent=('portal','Laya',{'selected':'portal'},{'choice':'portal'})
    def walk(folder,target,**kwargs):
        assert kwargs['approved_intent']==intent
        return []
    monkeypatch.setattr(portal,'walk',walk)
    monkeypatch.setattr(portal.interact,'use',lambda *_:{'completed':True})
    monkeypatch.setattr(portal.time,'sleep',lambda _:None)
    result=portal.run(tmp_path/'portal',{'from':entrance,'to':destination,'destination':'Tol Barad'},approved_intent=intent)
    assert result['completed'] and result['request']==intent[2]


def test_uldum_route_label_uses_the_observed_portal_name(monkeypatch,tmp_path):
    before=row();before['archaeology']['falling']=False
    destination={'instance':1,'north':-9444,'west':-959}
    after=copy.deepcopy(before);after['archaeology']['world']=destination
    frames=iter([before,before,before,before,after])
    monkeypatch.setattr(portal,'observe',lambda _:next(frames))
    monkeypatch.setattr(portal,'stationary',lambda *_:None)
    monkeypatch.setattr(portal.action_queue,'wait_stopped',lambda folder,row,observer:row)
    monkeypatch.setattr(portal,'align',lambda folder,row,target,**kwargs:[{'view_reset':kwargs['reset_view']}])
    monkeypatch.setattr(portal,'walk',lambda *_,**__:[])
    def interact(folder,row,names):
        assert 'Portal to Uldum' in names
        return {'completed':True}
    monkeypatch.setattr(portal.interact,'use',interact)
    monkeypatch.setattr(portal.time,'sleep',lambda _:None)
    result=portal.run(tmp_path/'portal',{'key':'org-uldum','from':{'instance':1,'north':21,'west':0},
        'to':destination,'destination':'Ramkahen (Uldum)'},approved_intent=('portal','Laya',{},{}))
    assert result['completed']


def test_named_portal_can_interact_before_reaching_an_obstructed_exact_coordinate(monkeypatch,tmp_path):
    before=row();before['archaeology']['falling']=False
    destination={'instance':1,'north':-9444,'west':-959}
    before['farm_ui']['soft_interact']['name']='Portal to Uldum'
    after=copy.deepcopy(before);after['archaeology']['world']=destination
    frames=iter([before,before,after])
    monkeypatch.setattr(portal,'observe',lambda _:next(frames))
    monkeypatch.setattr(portal,'stationary',lambda *_:None)
    monkeypatch.setattr(portal.action_queue,'wait_stopped',lambda folder,row,observer:row)
    monkeypatch.setattr(portal,'walk',lambda *_,**__:pytest.fail('named portal is already interactable'))
    monkeypatch.setattr(portal,'align',lambda *_,**__:pytest.fail('normal named interaction needs no camera reset'))
    monkeypatch.setattr(portal.interact,'use',lambda *_:{'completed':True})
    monkeypatch.setattr(portal.time,'sleep',lambda _:None)
    result=portal.run(tmp_path/'portal',{'key':'org-uldum','from':{'instance':1,'north':5,'west':0},
        'to':destination,'destination':'Ramkahen (Uldum)'},approved_intent=('portal','Laya',{},{}))
    assert result['completed'] and result['approach']['exact_coordinate_required'] is False


def test_verified_portal_view_approaches_the_successful_standing_position(monkeypatch,tmp_path):
    from . import portal_view
    before=row();before['archaeology']['falling']=False
    before['farm_ui']['soft_interact']['name']=None
    entrance={'instance':1,'north':21,'west':0}
    hint={'world':{'instance':1,'north':4,'west':2},'facing_radians':1.2,'zoom':5.55}
    destination={'instance':732,'north':-601,'west':1382}
    after=copy.deepcopy(before);after['archaeology']['world']=destination
    frames=iter([before,before,before,before,after])
    monkeypatch.setattr(portal,'observe',lambda _:next(frames))
    monkeypatch.setattr(portal,'stationary',lambda *_:None)
    monkeypatch.setattr(portal.action_queue,'wait_stopped',lambda folder,row,observer:row)
    monkeypatch.setattr(portal_view,'read',lambda *_:hint)
    monkeypatch.setattr(portal_view,'remember',lambda *_ ,**__:False)
    walks=[]
    monkeypatch.setattr(portal,'walk',lambda folder,target,**_:walks.append(target) or [])
    def align(folder,row,target,**kwargs):
        assert kwargs['reset_view']
        assert kwargs['zoom_target']==5.55
        assert target==portal_view.aim(hint,row)
        return []
    monkeypatch.setattr(portal,'align',align)
    monkeypatch.setattr(portal.interact,'use',lambda *_:{'completed':True})
    monkeypatch.setattr(portal.time,'sleep',lambda _:None)
    result=portal.run(tmp_path/'portal',{'key':'verified','from':entrance,
        'to':destination,'destination':'Tol Barad'},approved_intent=('portal','Laya',{},{}))
    assert result['completed'] and walks==[hint['world']]
