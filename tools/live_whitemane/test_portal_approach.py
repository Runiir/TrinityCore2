import copy
from . import portal
from .test_farm_loop import row


def test_portal_retains_its_selected_movement_intent_and_confirms_arrival(monkeypatch,tmp_path):
    before=row();before['archaeology']['falling']=False
    entrance={'instance':1,'north':21,'west':0}
    destination={'instance':732,'north':-601,'west':1382}
    after=copy.deepcopy(before);after['archaeology']['world']=destination
    frames=iter([before,before,before,after])
    monkeypatch.setattr(portal,'observe',lambda _:next(frames))
    monkeypatch.setattr(portal,'stationary',lambda *_:None)
    monkeypatch.setattr(portal,'choose',lambda *_,**kwargs:('portal',{}, {}, {}))
    walks=[]
    def walk(folder,target,**kwargs):
        walks.append(target)
        assert kwargs['approved_intent'][0]=='portal' and kwargs['tolerance']==2
        return []
    monkeypatch.setattr(portal,'walk',walk)
    monkeypatch.setattr(portal.interact,'use',lambda *_:{'completed':True})
    monkeypatch.setattr(portal.time,'sleep',lambda _:None)
    result=portal.run(tmp_path/'portal',{'from':entrance,'to':destination,'destination':'Tol Barad'})
    assert result['completed'] and walks==[entrance]
    assert 'turn_input' not in result
