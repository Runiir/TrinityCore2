import copy
import json
import math
from types import SimpleNamespace
import pytest
from PIL import Image,ImageDraw
from . import pending_find,minimap_finds,runtime,farm_loop,dig_session,telemetry_tiles
from .dig_policy import SolveBatches
from .test_farm_loop import row


@pytest.fixture
def owned_root(tmp_path,monkeypatch):
    (tmp_path/'run').mkdir();monkeypatch.setattr(runtime,'ROOT',tmp_path)
    return tmp_path


def test_out_of_range_latch_survives_reload_site_replacement_and_missing_blips(owned_root):
    r=row();r['movement']['facing_radians']=0
    r['archaeology'].update(site_id=331,looted_finds=3,successful_surveys=11,loot_open=False)
    value=pending_find.latch(r,site_id=331,approach={'world':{'instance':1,'north':8,'west':0}})
    pending_find.out_of_range(r,{'site_id':331})
    r['archaeology'].update(site_id=None,looted_finds=0,successful_surveys=0)
    r['minimap_finds']={'confirmed':[],'status':'no_visible_candidates','clear':True}
    assert pending_find.load(r)['out_of_range']
    assert not pending_find.can_leave(r)
    assert farm_loop.phase(r,SolveBatches(),True,pending_find.load(r))==('dig',None)
    r['archaeology']['races'][0]['fragments']+=5
    assert pending_find.load(r) is None and pending_find.can_leave(r)


def test_saved_markers_do_not_become_live_finds_but_a_filled_blip_can_overlap_them():
    im=Image.new('RGB',(100,100));draw=ImageDraw.Draw(im)
    draw.ellipse((25,25,35,35),outline=(255,230,30),width=1)
    geometry={'saved_pins':[{'x':30/runtime.WIDTH,'y':30/runtime.HEIGHT}]}
    assert minimap_finds.candidates(im,geometry,(0,0))==[]
    draw.ellipse((28,28,32,32),fill=(255,230,30))
    assert minimap_finds.candidates(im,geometry,(0,0))


def test_minimap_world_vector_respects_zoom_and_rotation():
    r=row();r['farm_ui']['minimap']={'x':.5,'y':.5,'width':100/runtime.WIDTH,
        'height':100/runtime.HEIGHT,'radius_yards':200,'rotating':False,'facing':math.pi/2}
    point={'x':runtime.WIDTH/2,'y':runtime.HEIGHT/2-25}
    assert minimap_finds.world_from_blip(r,point)=={'instance':1,'north':100,'west':0}
    r['farm_ui']['minimap']['rotating']=True
    p=minimap_finds.world_from_blip(r,point)
    assert abs(p['north'])<1e-10 and p['west']==100


def test_uninspected_blip_blocks_travel_and_confirmed_find_takes_priority():
    r=row();r['minimap_finds']={'status':'uninspected_candidates','confirmed':[],'clear':False}
    assert farm_loop.phase(r,SolveBatches(),True)[0]=='minimap'
    r['minimap_finds'].update(status='confirmed_finds',confirmed=[{'name':'Fossil Archaeology Find'}])
    assert farm_loop.phase(r,SolveBatches(),True)[0]=='dig'


def test_frozen_tiles_age_and_initial_or_reloaded_generations_are_not_assumed_fresh():
    generations={'M':2**32-1,'A':50,'F':60}
    clock=telemetry_tiles.GenerationClock(generations)
    clock.update(generations,10)
    assert clock.ages(10) is None
    generations={'M':0,'A':51,'F':61};clock.update(generations,10.2)
    assert clock.ages(10.2)['M']==pytest.approx(.075)
    clock.update(generations,12)
    assert clock.ages(12)['M']==pytest.approx(1.875)


def test_failed_pickup_measures_same_find_approach_instead_of_survey(owned_root,monkeypatch):
    r=row();r['movement']['facing_radians']=0;r['source']='test_public_observation'
    r['archaeology'].update(site_id=331,world={'instance':1,'north':0,'west':0},
        successful_surveys=0,last_survey_uptime_ms=0,looted_finds=0,loot_open=False,visible_markers=[])
    r['farm_ui']['soft_interact']['name']='Fossil Archaeology Find'
    r['farm_ui']['error']={'message':'Out of range.'}
    r['minimap_finds']={'status':'no_visible_candidates','confirmed':[],'clear':True}
    monkeypatch.setattr(dig_session,'observe',lambda _:copy.deepcopy(r))
    monkeypatch.setattr(dig_session.resources,'check',lambda **_:None)
    monkeypatch.setattr(dig_session,'choose',lambda _:('loot',{}, {},{}))
    monkeypatch.setattr(pending_find,'priority',lambda *_:{'choice':'pickup'})
    monkeypatch.setattr(dig_session.interact,'use',lambda *_:{'name':'Fossil Archaeology Find'})
    monkeypatch.setattr(dig_session.time,'sleep',lambda _:None)
    monkeypatch.setattr(dig_session.inputs,'execute',lambda *_:pytest.fail('no Survey or unrelated input allowed'))
    args=SimpleNamespace(output=owned_root/'dig',steps=1,loot_at=None,auto_loot=True)
    result=dig_session.run(args)
    assert result['failure'] is None
    value=pending_find.load(r)
    assert value['out_of_range'] and value['approach']['world']['north']==3
    session=json.loads((args.output/'session.json').read_text())
    assert session['steps'][-1]['outcome']=='out_of_range_approach_same_pending_find'


def test_survey_cooldown_wait_keeps_character_available_and_sends_no_requests(owned_root,monkeypatch):
    r=row();r['observed_at']=1;r['movement']['facing_radians']=0
    r['archaeology'].update(site_id=331,can_survey=True,successful_surveys=0,last_survey_uptime_ms=0,
        looted_finds=0,loot_open=False,visible_markers=[])
    r['farm_ui'].update(uptime=10,survey={'ready':False,'cooldown_ends':11})
    monkeypatch.setattr(dig_session,'observe',lambda _:copy.deepcopy(r))
    monkeypatch.setattr(dig_session.resources,'check',lambda **_:None)
    monkeypatch.setattr(dig_session,'choose',lambda _:pytest.fail('cooldown must not query Laya'))
    monkeypatch.setattr(dig_session.inputs,'execute',lambda *_:pytest.fail('cooldown must not send input'))
    monkeypatch.setattr(dig_session.time,'sleep',lambda _:None)
    assert dig_session.routes.model_state(r,None,False)['available']
    args=SimpleNamespace(output=owned_root/'dig',steps=1,loot_at=None,auto_loot=True)
    assert dig_session.run(args)['failure'] is None
    session=json.loads((args.output/'session.json').read_text())
    assert session['steps']==[]
    assert session['survey_cooldown_wait']['remaining_seconds']==1
