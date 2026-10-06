import copy
import json
import struct
from types import SimpleNamespace
import pytest
from tools.live_whitemane import farm_ui, farm_loop, interact, farm_actions
from tools.live_whitemane.dig_policy import SolveBatches
from tools.client_compatibility.observation.telemetry import checksum


def packet(value):
    payload=json.dumps(value).encode();body=b'TCU3'+struct.pack('>HI',len(payload),7)+payload
    return body+checksum(body).to_bytes(2,'big')


def row():
    return {'observed_at':1,'runtime':{'pid':1},'movement':{'in_world':True,'position_available':True,'health_percent':100,
        'in_combat':False,'dead':False,'on_taxi':False,'map_id':1454,'speed':0},
        'archaeology':{'mounted':False,'flying':False,'casting':False,'recipe_items_in_bags':0,
        'canopic_jars_in_bags':0,'can_survey':False,'world':{'instance':1,'north':0,'west':0},
        'races':[{'index':7,'fragments':149,'cost':45,'sockets':2,'keystones_in_bags':0,'project_spell':91769}]},
        'farm_ui':{'recipe_known':False,'route':{'kind':'shortcut'},
            'soft_interact':{'enabled':'3','exists':False,'name':'Portal to Orgrimmar'},
            'bindings':{'INTERACTTARGET':['9']}}}


def test_public_ui_checksum_capacity_and_non_objects():
    assert farm_ui.decode(packet({'text':'x'*12000}))['sequence']==7
    corrupted=bytearray(packet({'foo':2}));corrupted[11]^=1
    with pytest.raises(ValueError,match='checksum'):farm_ui.decode(corrupted)
    with pytest.raises(ValueError,match='invalid farm UI'):farm_ui.decode(packet([]))
    with pytest.raises(ValueError,match='capacity'):farm_ui.decode(packet({'observer_error':'capacity'}))


def test_final_pending_loot_precedes_travel_and_solving():
    r=row();r['farm_ui']['route']['kind']='pending_loot';r['archaeology']['races'][0]['fragments']=160
    assert farm_loop.phase(r,SolveBatches(),True)==('dig',None)


def test_solve_threshold_and_active_batch_are_kept_across_loop_steps():
    r=row();b=SolveBatches()
    assert farm_loop.phase(r,b)[0]=='teleport'
    r['archaeology']['races'][0]['fragments']=150
    assert farm_loop.phase(r,b)[0]=='solve'
    r['archaeology']['races'][0]['fragments']=50
    assert farm_loop.phase(r,b)[0]=='solve'
    r['archaeology']['races'][0]['fragments']=20
    assert farm_loop.phase(r,b)[0]=='teleport'


def test_existing_digsite_is_finished_before_next_travel_and_recipe_stops_input():
    r=row();r['archaeology']['can_survey']=True
    assert farm_loop.phase(r,SolveBatches(),True)[0]=='dig'
    r['archaeology']['recipe_items_in_bags']=1;r['archaeology']['canopic_jars_in_bags']=1
    assert farm_loop.phase(r,SolveBatches(),True)[0]=='recipe'
    r['farm_ui']=None
    assert farm_loop.phase(r,SolveBatches(),True)[0]=='wait'


def test_active_digsite_navigation_is_not_replaced_with_a_flight_to_its_center():
    from . import farm_policy
    r=row();r['archaeology'].update(can_survey=True,site_id=315,falling=False)
    r['farm_ui']['route'].update(kind='dig',site={'point':{'instance':1,'north':30,'west':0}})
    guide={'arrived':False,'color':'green','world':{'instance':1,'north':5,'west':0}}
    actions=farm_policy.legal_actions(r,SolveBatches(),guide)
    assert 'dig' in actions and 'flight' not in actions
    flight=farm_policy.legal_actions(r,SolveBatches(),guide,ground_approach_blocked=True)['flight'][1]
    assert flight['north']==5 and flight['arrival_tolerance_yards']==.5
    assert flight['site_id']==315
    r['archaeology']['can_survey']=False
    assert 'flight' in farm_policy.legal_actions(r,SolveBatches())


def test_grounded_mount_can_enter_dig_without_a_separate_dismount_but_airborne_cannot():
    from . import farm_policy,dig_session
    r=row();r['archaeology'].update(can_survey=True,mounted=True,falling=False)
    assert 'dig' in farm_policy.legal_actions(r,SolveBatches()) and dig_session.healthy(r)
    r['archaeology']['flying']=True
    assert 'dig' not in farm_policy.legal_actions(r,SolveBatches()) and not dig_session.healthy(r)


def test_combat_root_choice_uses_immediate_facts_and_preserves_all_legal_actions(monkeypatch):
    from . import farm_policy
    r=row();r['movement']['in_combat']=True;r['archaeology'].update(mounted=True,flying=True,falling=False)
    r['farm_ui']['combat']={'target_name':'Attacker','target_attacks_player':True,'attack_in_range':False}
    session={'via_tolbarad':True,'steps':[],'dig_site':None,'dig_output':None,'active_races':[]}
    legal=farm_policy.legal_actions(r,SolveBatches())
    def choose(state,instructions,options):
        assert set(options)==set(legal)
        assert state['combat'] and state['flying'] and state['target_attacks_player']
        assert 'fragments' not in state and 'route_instruction' not in state
        return 'combat',{},{}
    monkeypatch.setattr(farm_policy.laya_ui,'choose',choose)
    assert farm_policy.choose(r,SolveBatches(),session)[0]=='combat'


def test_travel_context_fits_immediate_route_facts_without_dropping_legal_choices(monkeypatch):
    from . import farm_policy
    r=row();r['archaeology'].update(falling=False,swimming=False,grounded=True)
    r['farm_ui']['route'].update(kind='taxi',instruction='Approach Doras then take instant taxi',
        origin={'point':{'instance':1,'north':100,'west':0}},exit={'id':531})
    session={'via_tolbarad':True,'steps':[],'dig_site':None,'dig_output':None,'active_races':[]}
    legal=farm_policy.legal_actions(r,SolveBatches())
    def choose(state,instructions,options):
        assert set(options)==set(legal)
        assert state['next_waypoint_is_flight_master'] and state['grounded']
        assert state['task']=='Follow addon next leg: Approach Doras then take instant taxi'
        assert 'fragments' not in state
        return 'flight',{},{}
    monkeypatch.setattr(farm_policy.laya_ui,'choose',choose)
    action,target,decision=farm_policy.choose(r,SolveBatches(),session)
    assert action=='flight' and target['north']==100
    assert decision['observed_state']['fragments'][0]['fragments']==149


def test_shortcut_keeps_a_future_flight_master_out_of_the_active_route_leg():
    from . import farm_policy
    r=row();r['archaeology']['falling']=False
    r['farm_ui']['actionbars']=[{'enabled':True,'kind':'spell','id':5000028,'label':'Teleport: Tol Barad'}]
    r['farm_ui']['route'].update(origin={'point':{'instance':1,'north':9000,'west':0}},
        exit={'point':{'instance':1,'north':9000,'west':4000}})
    actions=farm_policy.legal_actions(r,SolveBatches())
    assert 'teleport' in actions and 'flight' not in actions
    r['farm_ui']['route']['kind']='taxi'
    actions=farm_policy.legal_actions(r,SolveBatches())
    assert 'flight' in actions and 'teleport' not in actions


def test_portal_route_keeps_future_taxi_and_other_nearby_portals_from_overwriting_next_leg():
    from . import farm_policy
    r=row();r['archaeology']['falling']=False;r['farm_ui']['flyable']=True
    portal={'key':'selected','destination':'Selected','from':{'instance':1,'north':5,'west':0}}
    other={'key':'other','destination':'Other','from':{'instance':1,'north':10,'west':0}}
    r['farm_ui']['route'].update(kind='portal',portal=portal,known_portals=[portal,other],
        origin={'point':{'instance':1,'north':500,'west':0}},exit={'id':531})
    actions=farm_policy.legal_actions(r,SolveBatches())
    assert actions['portal'][1]==portal and actions['flight'][1]['north']==5
    assert actions['portal_other'][1]==other and actions['flight_portal_other'][1]['north']==10
    assert 'taxi' not in actions


@pytest.mark.parametrize('flag',['mounted','flying','falling'])
def test_server_teleport_rejects_mount_or_airborne_state_and_keeps_landing_available(flag):
    from . import farm_policy
    r=row();r['archaeology'].update({'falling':False,flag:True})
    r['farm_ui']['actionbars']=[{'enabled':True,'kind':'spell','id':5000028,'label':'Teleport: Tol Barad'}]
    actions=farm_policy.legal_actions(r,SolveBatches())
    assert 'teleport' not in actions and 'land' in actions


def test_named_game_object_soft_target_can_use_interact_without_unit_exists(monkeypatch,tmp_path):
    monkeypatch.setattr(farm_loop.runtime,'ROOT',tmp_path)
    r=row();monkeypatch.setattr(interact,'observe',lambda _:copy.deepcopy(r))
    monkeypatch.setattr(interact,'stationary',lambda *_:None)
    calls=[];monkeypatch.setattr(interact.inputs,'execute',lambda *args:calls.append(args) or {'completed':True})
    result=interact.use(tmp_path/'use',r,{'Portal to Orgrimmar'})
    assert result['name']=='Portal to Orgrimmar'
    assert calls==[('World of Warcraft','key',{'key':'9','hold':.15})]


def test_wrong_ui_destination_is_rejected_before_any_input(monkeypatch,tmp_path):
    r=row();r['farm_ui']['buttons']=[{'label':'Wrong destination','enabled':True,'x':.5,'y':.5}]
    monkeypatch.setattr(farm_actions.laya_ui,'choose',lambda *_:('button_0',{},{}))
    monkeypatch.setattr(farm_actions.inputs,'execute',lambda *_:pytest.fail('must not send wrong destination'))
    with pytest.raises(RuntimeError,match='inconsistent'):
        farm_actions.click_choice(tmp_path/'choice',r,['buttons'],'Tol Barad',{'label':'Tol Barad'})


def test_observer_panels_do_not_overlap_at_the_live_scale():
    # Normal addon anchors are scaled by 1.17 in this owned client. The UI
    # packet's complete maximum-height rectangle must clear both bit panels.
    archaeology=(16,76,16+288,76+129)
    ui=(340,16,340+128*3,16+((16384+12+383)//384)*3)
    assert ui[0]>=archaeology[2]


def test_open_taxi_map_remains_a_taxi_phase_when_route_origin_is_omitted():
    r=row();r['farm_ui']['route'].update(kind='site',current_taxi=23,
        exit={'id':79,'point':{'instance':1,'north':-7548,'west':-1541}},
        site={'point':{'instance':1,'north':-7815,'west':-692}})
    r['farm_ui']['taxi']=[{'id':23,'label':'Orgrimmar, Durotar'},{'id':79,'label':"Marshal's Stand"}]
    selected,target=farm_loop.phase(r,SolveBatches())
    assert selected=='taxi' and target[0]['id']==23 and target[1]['id']==79


def test_large_rgb_packet_requires_checksum_valid_scale_calibration():
    from PIL import Image,ImageDraw
    encoded=packet({'text':'abcdefghijklm'*850});cell=3.515625;x=398;y=17.5
    encoded+=b'\0'*(-len(encoded)%3)
    image=Image.new('RGB',(1280,900));draw=ImageDraw.Draw(image)
    for i in range(len(encoded)//3):
        left,top=x+(i%128)*cell,y+(i//128)*cell
        draw.rectangle((int(left),int(top),int(left+cell)-1,int(top+cell)-1),fill=tuple(encoded[i*3:i*3+3]))
    value,calibration=farm_ui.recalibrate(image,{'x':398.245,'y':17.245,'cell':3.51})
    assert value['text']=='abcdefghijklm'*850
    assert farm_ui.decode_image(image,**calibration)['text']==value['text']


def test_retryable_failure_inside_recovery_returns_to_observation(monkeypatch,tmp_path):
    from . import observed_state
    monkeypatch.setattr(farm_loop.runtime,'ROOT',tmp_path)
    (tmp_path/'run').mkdir();r=row()
    monkeypatch.setattr(farm_loop.runtime,'owned_process',lambda:r['runtime'])
    r['archaeology'].update(site_id=None,loot_open=False,falling=False)
    monkeypatch.setattr(farm_loop.resources,'enable',lambda:None)
    monkeypatch.setattr(farm_loop.resources,'check',lambda **_:None)
    monkeypatch.setattr(farm_loop.resources,'phase_boundary',lambda *_:None)
    monkeypatch.setattr(observed_state,'ensure',lambda _:None)
    monkeypatch.setattr(farm_loop.farm_graph,'transition',lambda *_,**__:None)
    monkeypatch.setattr(farm_loop.farm_policy,'choose',lambda *_:('land',r['archaeology']['world'],{}))
    def failed(*_,**__):raise RuntimeError('dismount input did not produce unmounted state')
    monkeypatch.setattr(farm_loop,'fly',failed)
    monkeypatch.setattr(farm_loop.recovery,'run',failed)
    observations=[0]
    def observe(_):
        observations[0]+=1
        if observations[0]==3:(tmp_path/'run/stop_dig').touch()
        return copy.deepcopy(r)
    monkeypatch.setattr(farm_loop,'observe',observe)
    output=tmp_path/'farm';output.mkdir()
    (output/'loop.json').write_text(json.dumps({'status':'repair_required','failure':'old failure',
        'active_races':[],'steps':[],'last_progress_at':0,'completed_sites':0,'looted_finds':0,
        'dig_output':None,'dig_site':None,'via_tolbarad':False}))
    result=farm_loop.run(output)
    assert result['status']=='supervisor_stopped' and result['failure'] is None
    session=json.loads((tmp_path/'farm/loop.json').read_text())
    assert session['resumed_at']>0
    assert session['steps'][-1]['recovery']['outcome']=='reobserve_with_Laya_on_next_loop'


@pytest.mark.parametrize('in_combat',[False,True])
def test_dig_intent_survives_a_recoverable_stall_or_combat(monkeypatch,tmp_path,in_combat):
    from . import observed_state
    from .intent_queue import IntentQueue
    monkeypatch.setattr(farm_loop.runtime,'ROOT',tmp_path);(tmp_path/'run').mkdir()
    r=row();r['archaeology'].update(can_survey=True,site_id=315,loot_open=False,falling=False)
    monkeypatch.setattr(farm_loop.runtime,'owned_process',lambda:r['runtime'])
    monkeypatch.setattr(farm_loop.resources,'enable',lambda:None)
    monkeypatch.setattr(farm_loop.resources,'check',lambda **_:None)
    monkeypatch.setattr(farm_loop.resources,'phase_boundary',lambda *_:None)
    monkeypatch.setattr(observed_state,'ensure',lambda _:None)
    monkeypatch.setattr(farm_loop.farm_graph,'transition',lambda *_,**__:None)
    def choose(row,batches,session):
        IntentQueue(session).offer('dig',None,{'choice':'dig'},row)
        return 'dig',None,{}
    monkeypatch.setattr(farm_loop.farm_policy,'choose',choose)
    monkeypatch.setattr(farm_loop.dig_session,'run',lambda *_:{'finished':False,
        'failure':'continuous waypoint movement is blocked'})
    monkeypatch.setattr(farm_loop.recovery,'run',lambda *_:{'completed':True})
    def observe(path):
        value=copy.deepcopy(r)
        if path.name!='before.png':value['movement']['in_combat']=in_combat
        if path.name=='after.png':(tmp_path/'run/stop_dig').touch()
        return value
    monkeypatch.setattr(farm_loop,'observe',observe)
    result=farm_loop.run(tmp_path/'farm')
    assert result['status']=='supervisor_stopped' and result['failure'] is None
    session=json.loads((tmp_path/'farm/loop.json').read_text())
    assert session['accepted_activity_queue'][0]['action']=='dig'
    assert IntentQueue(session).retained(r,{'dig':('',None)})[0]=='dig'


@pytest.mark.parametrize('blocked_fact',['flying','other_site','pending',None])
def test_interrupted_root_landing_hands_back_to_survey_only_on_current_digsite_ground(monkeypatch,tmp_path,blocked_fact):
    monkeypatch.setattr(farm_loop.pending_find,'load',lambda _:{'site_id':315} if blocked_fact=='pending' else None)
    r=row();r['archaeology'].update(can_survey=True,site_id=315,falling=False)
    if blocked_fact=='flying':r['archaeology']['flying']=True
    if blocked_fact=='other_site':r['archaeology']['site_id']=321
    path=tmp_path/'session.json';original={'telescope_target':{},'last_green_endpoint':{},'marker_target':{}}
    path.write_text(json.dumps(original))
    step={'phase':'flight','completed':False,'target':{'instance':1,'north':1,'west':0},
        'travel_decisions':[{'action':'land'}]}
    session={'steps':[step],'dig_site':315,'dig_output':str(tmp_path)}
    farm_loop.resume_grounded_flight(session,r)
    dig=json.loads(path.read_text())
    if blocked_fact:assert dig==original and 'grounded_digsite_reobserve' not in step
    else:
        assert dig=={'marker_target':{},'walked_since_survey':True}
        assert not step['grounded_digsite_reobserve']['destination_arrival_confirmed']
