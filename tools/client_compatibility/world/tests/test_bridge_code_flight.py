import urllib.request
from PIL import Image
from tools.client_compatibility import bridge_travel_probe as probe,site_boundaries


def setup(monkeypatch,tmp_path,health=100,progress=True):
    position=[0,0,0,0];extra={'mounted':False,'flying':False,'falling':False,'swimming':False,'casting':False}
    facts={'position':position,'map':0,'transferring':False};actions=[]
    class Observer:
        guid=1;session='owned'
        def poll(self):return {**facts,'position':position[:]}
    def screenshot(path):
        Image.new('RGB',(8,8)).save(path)
        return {'in_world':True,'health_percent':health,'dead':False,'in_combat':False,'on_taxi':False},extra.copy()
    def execute(action,*args):
        actions.append(action)
        if progress:
            if action=='mount':extra['mounted']=True
            elif action=='takeoff':extra['flying']=True;position[2]=8
            elif action=='cruise':position[0]=7
            elif action=='land':extra['flying']=False;position[2]=0
            elif action=='dismount':extra['mounted']=False
        return {'physical_keys':[action]}
    def no_http(*args,**kwargs):raise AssertionError('a model endpoint must never be called')
    monkeypatch.setattr(urllib.request,'urlopen',no_http)
    monkeypatch.setattr(probe,'Observer',Observer)
    monkeypatch.setattr(probe.archaeology_inputs,'screenshot',screenshot)
    monkeypatch.setattr(probe.travel_inputs,'execute',execute)
    monkeypatch.setattr(probe.owned_input,'focus',lambda:{'monitor':{'name':'HDMI-1'}})
    monkeypatch.setattr(probe.lab,'owned_process',lambda name:{'engine':'cpp'})
    monkeypatch.setattr(probe.taxi,'decode_image',lambda image:{'nodes':[]})
    monkeypatch.setattr(site_boundaries,'sites',lambda:{207:{'map':0,'polygon':[[-2,-2],[10,-2],[10,2],[-2,2]]}})
    plan={'green_terrain_recovery':{'site_id':207,'start':[0,0,0]},'legs':[
        {'mode':'flight','map':0,'position':[7,0,0],'ceiling':8,'arrival_radius':1.5,
         'landing_height_tolerance':2,'landing_avoidance_frozen':True}]}
    return probe.run(plan,tmp_path/'flight'),actions


def test_complete_physical_flight_never_calls_a_model(monkeypatch,tmp_path):
    result,actions=setup(monkeypatch,tmp_path)
    assert result['completed'] and result['model_called'] is False
    assert actions==['mount','takeoff','cruise','land','dismount','arrived']
    assert result['finished_at'] and len(result['frames'])==6


def test_unsafe_health_closes_without_any_input(monkeypatch,tmp_path):
    result,actions=setup(monkeypatch,tmp_path,health=40)
    assert not result['completed'] and result['finished_at']
    assert 'unsafe state' in result['failure'] and actions==[]


def test_failed_mount_does_not_toggle_forever(monkeypatch,tmp_path):
    result,actions=setup(monkeypatch,tmp_path,progress=False)
    assert not result['completed'] and result['finished_at']
    assert 'without phase progress' in result['failure'] and len(actions)==5
