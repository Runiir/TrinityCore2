from tools.client_compatibility import client_floor_probe as probe,site_boundaries


def test_ground_contact_requires_an_owned_site_and_cannot_be_accepted_in_air():
    site=site_boundaries.sites()[399]
    leg={'site_id':399,'map':530,'position':[-4183,400.416656,49.1118813]}
    facts={'map':530,'position':[-4177.8047,401.3046,60.799,0]}
    extra=dict(mounted=True,flying=False,falling=False,swimming=False)
    assert probe.needed(facts,extra,leg)
    assert site_boundaries.contains(site['polygon'],facts['position'])
    assert not probe.needed(facts,{**extra,'flying':True},leg)
    assert not probe.needed(facts,{**extra,'swimming':True},leg)
    assert not probe.needed(facts,extra,{**leg,'site_id':None})
    assert not probe.needed({**facts,'position':[-4177.8,401.3,100,0]},extra,leg)


def test_stale_survey_marker_cannot_validate_client_floor(monkeypatch,tmp_path):
    import pytest
    from tools.client_compatibility import archaeology_inputs
    from tools.client_compatibility.observation import archaeology
    position=[-4177.8047,401.3046,60.799,0];extra=dict(mounted=True,flying=False,falling=False,swimming=False)
    class Inputs:
        def key(self,key):
            if key=='3':extra['mounted']=False
    class Transport:
        def poll(self):return {'map':530,'position':position.copy()}
    class Objects:
        def poll(self,_):return {'tool':{'map':530,'seen_at':0},'finds':[]}
    monkeypatch.setattr(probe.owned_input,'Inputs',Inputs)
    monkeypatch.setattr(probe.time,'sleep',lambda _:None)
    monkeypatch.setattr(archaeology,'Observer',Objects)
    monkeypatch.setattr(probe.ground_navigation,'water_at',lambda *_:{'water_above_feet':False})
    monkeypatch.setattr(archaeology_inputs,'screenshot',lambda _:(
        {'in_world':True,'health_percent':100,'dead':False,'in_combat':False,'on_taxi':False},extra))
    leg={'site_id':399,'map':530,'position':[-4183,400.416656,49.1118813]}
    with pytest.raises(RuntimeError,match='no fresh owned'):
        probe.verify(leg,Transport(),tmp_path/'latest.png')
    assert leg['position']==[-4183,400.416656,49.1118813] and not leg.get('verified_client_floor')
