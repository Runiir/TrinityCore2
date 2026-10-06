import copy
import pytest
from . import taxi
from .test_farm_loop import row


@pytest.mark.parametrize('frame_rate,hold',[(None,.15),(30,.15),(1,2)])
def test_taxi_honors_model_landing_then_dismount_before_arrival(monkeypatch,tmp_path,frame_rate,hold):
    air=row();air['archaeology'].update(mounted=True,flying=True,falling=False)
    air['farm_ui']['frame_rate']=frame_rate
    ground=copy.deepcopy(air);ground['archaeology']['flying']=False
    foot=copy.deepcopy(ground);foot['archaeology']['mounted']=False
    target=air['archaeology']['world']
    origin={'id':23,'point':target};destination={'id':99,'point':target}
    observations=iter([air,ground,foot])
    decisions=iter(['land','dismount','arrived'])
    monkeypatch.setattr(taxi,'observe',lambda _:next(observations))
    monkeypatch.setattr(taxi,'choose',lambda *_,**kw:(next(decisions),{'model':'retained head'},{},{}))
    landings=[]
    monkeypatch.setattr(taxi,'descend',lambda folder,point:landings.append(point) or ['ground confirmed'])
    commands=[]
    monkeypatch.setattr(taxi.inputs,'execute',lambda *args:commands.append(args[-1]) or args[-1])
    def queue(folder,before,name,send,confirmed,observer,**kwargs):
        assert name=='dismount' and kwargs['allowed'](ground)
        assert not kwargs['allowed'](air) and confirmed(foot) and not confirmed(ground)
        return {'inputs':[send(before)],'state':'confirmed'}
    monkeypatch.setattr(taxi.action_queue,'run',queue)
    result=taxi.run(tmp_path/'taxi',origin,destination)
    assert result['completed'] and [p['action'] for p in result['phases']]==['land','dismount','arrived']
    assert landings==[target] and commands==[{'key':'shift+space','hold':hold}]
