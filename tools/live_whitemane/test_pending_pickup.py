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


def test_old_green_endpoint_cannot_send_a_new_pickup_back_across_the_site(owned_root):
    r=row();r['archaeology'].update(site_id=331,looted_finds=0,loot_open=False)
    old={'world':{'instance':1,'north':125,'west':0}}
    value=pending_find.latch(r,approach=old)
    assert value['approach'] is None
    value['approach']=old;runtime.write(owned_root/'run/pending_find.json',value)
    session={'pickup_approach':old,'reapproach_find':True}
    updated=pending_find.update(r,session)
    assert updated and updated['approach'] is None
    assert 'pickup_approach' not in session and not session['reapproach_find']


def test_minimap_inspection_retains_one_sender_until_all_cursor_probes_finish(owned_root,monkeypatch):
    from . import observe,interact,farm_actions
    from tools.client_compatibility import native_input_adapter
    r=row();r['farm_ui']['minimap']={'x':.5,'y':.5,'width':.1,'height':.1,
        'radius_yards':200,'rotating':False,'zoom':0}
    points=[{'x':640,'y':440},{'x':640,'y':450}]
    monkeypatch.setattr(minimap_finds,'signal',lambda *_,**__:{'candidates':points})
    monkeypatch.setattr(minimap_finds.laya_ui,'choose',lambda *_:('inspect',{},{}))
    monkeypatch.setattr(observe,'observe',lambda _:r)
    monkeypatch.setattr(farm_actions,'stationary',lambda *_:None)
    monkeypatch.setattr(minimap_finds.inputs,'focus',lambda _:{'owned':True})
    monkeypatch.setattr(minimap_finds.inputs,'execute',lambda *_:pytest.fail('must retain the inspection sender'))
    senders=[]
    class Sender:
        def __init__(self):self.initialization={'owned':True};self.closed=False;senders.append(self)
        def close(self):self.closed=True
    monkeypatch.setattr(native_input_adapter,'Input',Sender)
    def hover(sender,point,*_):
        assert len(senders)==1 and not sender.closed
        result=copy.deepcopy(r)
        result['farm_ui']['minimap']['tooltip_lines']=(['NPC'] if point[1]==440 else ['Fossil Archaeology Find'])
        return result
    monkeypatch.setattr(interact,'hover',hover)
    result=minimap_finds.inspect(owned_root/'scan',r)
    assert len(result['probes'])==2 and senders[0].closed
    assert result['all_candidates_inspected'] and len(result['confirmed'])==1


def test_verified_pickup_counter_can_confirm_collection_after_currency_spending(owned_root):
    r=row();r['archaeology'].update(looted_finds=3,loot_open=False,site_id=331)
    r['archaeology']['races'][0]['fragments']=100
    pending_find.latch(r)
    r['archaeology']['races'][0]['fragments']=5
    assert pending_find.load(r)
    r['archaeology']['looted_finds']=4
    assert pending_find.load(r) is None


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


def test_captured_find_coordinates_prevent_travel_after_the_final_survey(owned_root):
    from . import world_facts,farm_policy
    from .survey_find import collected
    r=row();r['archaeology'].update(can_survey=False,site_id=None,loot_open=False,falling=False)
    find={'world':{'instance':1,'north':8,'west':0},'observed_at':50,'runtime':r['runtime'],
        'source':'owned_authenticated_visible_find_create_after_own_survey','estimated_position':False}
    r['visible_find']=find
    assert world_facts.reduce(r)['activity']=='pickup'
    assert not pending_find.facts(r,None)['position_is_estimate']
    pending=pending_find.update(r,{})
    r['pending_find']=pending
    assert pending['approach']['world']==find['world']
    assert 'dig' in farm_policy.legal_actions(r,SolveBatches())
    assert 'teleport' not in farm_policy.legal_actions(r,SolveBatches())
    session={};pending_find.out_of_range(r,session)
    assert session['pickup_approach']['world']==find['world']
    r['archaeology']['races'][0]['fragments']+=5
    assert pending_find.update(r,{}) is None and r['visible_find'] is None
    assert world_facts.reduce(r)['activity']=='travel'
    assert collected(find)


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


def test_partial_tooltip_search_preserves_pending_find_without_obstacle_recovery(owned_root,monkeypatch):
    r=row();r['movement']['facing_radians']=0;r['source']='test_public_observation'
    r['archaeology'].update(site_id=331,successful_surveys=0,last_survey_uptime_ms=0,
        looted_finds=0,loot_open=False,visible_markers=[])
    r['farm_ui']['soft_interact']['name']='Fossil Archaeology Find'
    pending_find.latch(r)
    monkeypatch.setattr(dig_session,'observe',lambda _:copy.deepcopy(r))
    monkeypatch.setattr(dig_session.resources,'check',lambda **_:None)
    monkeypatch.setattr(dig_session,'choose',lambda _:('loot',{}, {},{}))
    monkeypatch.setattr(pending_find,'priority',lambda *_:{'choice':'pickup'})
    def partial(*_):raise RuntimeError('named interaction search yielded for fresh facts')
    monkeypatch.setattr(dig_session.interact,'use',partial)
    monkeypatch.setattr(dig_session.inputs,'execute',lambda *_:pytest.fail('no extra input'))
    args=SimpleNamespace(output=owned_root/'dig',steps=1,loot_at=None,auto_loot=True)
    result=dig_session.run(args)
    assert result['failure'] is None and result['stop_reason'] is None
    session=json.loads((args.output/'session.json').read_text())
    step=session['steps'][-1]
    assert step['completed'] and step['outcome']=='interaction_search_incomplete'
    assert not step['confirmed_looted_find']
    assert pending_find.load(r) and not pending_find.load(r).get('tooltip_search_misses')


def test_collected_tooltip_cannot_relatch_a_find_before_the_next_survey(owned_root):
    r=row();r['observed_at']=10
    r['archaeology'].update(site_id=315,successful_surveys=30,looted_finds=8,loot_open=False)
    r['farm_ui']['tooltip']='Troll Archaeology Find'
    pending_find.confirm_pickup(r)
    assert not pending_find.named_uncollected(r)
    assert pending_find.update(r,{}) is None
    r['archaeology']['successful_surveys']=31
    assert pending_find.named_uncollected(r) and pending_find.update(r,{})


def test_new_located_find_overrides_a_lingering_collected_tooltip(owned_root):
    r=row();r['observed_at']=10
    r['archaeology'].update(site_id=315,successful_surveys=30,looted_finds=8,loot_open=False)
    r['farm_ui']['tooltip']='Troll Archaeology Find'
    pending_find.confirm_pickup(r)
    r['minimap_finds']={'confirmed':[{'world':r['archaeology']['world'],'name':'Troll Archaeology Find'}]}
    assert pending_find.named_uncollected(r) and pending_find.update(r,{})


def test_confirmed_pickup_repairs_a_prior_tooltip_only_phantom_latch(owned_root):
    r=row();r['observed_at']=10
    r['archaeology'].update(site_id=315,successful_surveys=30,looted_finds=8,loot_open=False)
    r['farm_ui']['tooltip']='Troll Archaeology Find'
    value=pending_find.latch(r,source='public visible archaeology find')
    assert value['discovery_confirmed']
    pending_find.confirm_pickup(r)
    assert pending_find.load(r) is None and pending_find.update(r,{}) is None
