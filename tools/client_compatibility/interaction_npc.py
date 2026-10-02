"""Probe one existing NPC service through normal observed mouse inputs."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_operations import click_case,controls
from .interaction_macros import require
from .npc_fixture import NpcFixture


SERVICES={
    'merchant':{'entry':1285,'flag':128,'panel':'MerchantFrame','caption':'goods'},
    'repair':{'entry':1324,'flag':4096,'panel':'MerchantFrame','caption':'goods'},
    'trainer':{'entry':5479,'flag':16,'panel':'ClassTrainerFrame','caption':'train'},
    'profession-trainer':{'entry':5499,'flag':16,'panel':'ClassTrainerFrame','caption':'train'},
}


def suite(t,service,point,stage_only,sell_buyback=False,purchase=False,repair_all=False,learn=False,camera_zoom=None,camera_drag_y=0):
    spec=SERVICES[service];actors.session_entry(t.fixture);t.clean_panels()
    fixture=NpcFixture(t.out,t.fixture,spec['entry'],spec['flag']);camera_before=None;camera_dragged=False
    try:
        fixture.prepare();t.execute({'kind':'chat','value':'/targetexact '+fixture.npc[2]})
        if camera_zoom is not None:
            from .interaction_camera_fixture import zoom,set_zoom
            camera_before,_=zoom(t,'camera_baseline');set_zoom(t,camera_zoom,'camera_setup',tolerance=.51)
        if camera_drag_y:
            t.io.drag((900,360),(900,360+camera_drag_y));camera_dragged=True
            t.receipt['camera_drag_fixture']={'source':'code_fixture_left_mouse_drag','delta_y':camera_drag_y,'reversed':False,
                'limit':'Opposite physical drag verified; camera pitch has no observation oracle.'};t.persist()
        state,frame=t.observe('npc_staged');t.receipt['staging']={'target':state['target'],'frame':frame};t.persist()
        if state['target'].get('name')!=fixture.npc[2] or not state['target'].get('visible'):
            raise RuntimeError('service NPC is not visibly targeted')
        if stage_only:return
        require(t.step(service+'.interact','Speak to the nearby '+service+' '+fixture.npc[2]+'.',{
            'interact':{'kind':'click','value':point,'button':3,'description':'Right-click the visible nearby '+service+' '+fixture.npc[2]+'.'},
            'map':{'kind':'key','value':'m','description':'Open the world map.'},
            'character':{'kind':'key','value':'c','description':'Open your character equipment.'}},
            lambda b,a,s:{'status':'npc_interaction_pass' if s=='interact' and any(p in a['panels'] for p in [spec['panel'],'GossipFrame']) else
                ('controller_failure' if s!='interact' else 'client_or_protocol_failure'),'oracle':{'panels':a['panels'],'errors':a['errors']}},
            diagnostic_action='interact'),'npc_interaction_pass')
        state,_=t.observe('npc_response')
        if 'GossipFrame' in state['panels']:
            require(click_case(t,service+'.gossip','Open the '+service+' service.',lambda c:spec['caption'] in c['text'].lower(),
                lambda b,a,s:{'status':'service_open_pass' if s and spec['panel'] in a['panels'] else
                    ('controller_failure' if not s else 'client_or_protocol_failure'),'oracle':{'panels':a['panels'],'errors':a['errors']}}),'service_open_pass')
        state,frame=t.observe('service_open');t.receipt['service_open']={'state':state,'frame':frame,'controls':controls(t)};t.persist()
        if spec['panel'] not in state['panels']:raise RuntimeError('service window is absent')
        if service=='merchant':
            with lab.connection() as c,c.cursor() as q:
                q.execute('SELECT item FROM client442_world.npc_vendor WHERE entry=%s AND type=1 AND PlayerConditionID=0 ORDER BY slot',(spec['entry'],))
                expected=[r[0] for r in q.fetchall()]
            visible=[r['id'] for r in state.get('merchant',{}).get('items',[])]
            matches=expected==visible and state.get('merchant',{}).get('count')==len(expected)
            t.receipt['merchant_catalog_oracle']={'native_vendor_item_ids':expected,'visible_item_ids':visible,'matches':matches};t.persist()
            if not matches:raise RuntimeError('visible merchant catalog disagrees with the existing native vendor fixture')
        if sell_buyback:
            from .interaction_merchant_items import roundtrip
            roundtrip(t)
        if purchase:
            from .interaction_merchant_purchase import buy
            buy(t)
        if repair_all:
            from .interaction_repairs import repair_all as repair
            repair(t)
        if learn:
            from .interaction_trainer_learning import learn_selected
            learn_selected(t)
        require(t.step(service+'.close','Close the '+service+' window.',{
            'close':{'kind':'key','value':'Escape','description':'Press Escape to close the '+service+' window.'},
            'map':{'kind':'key','value':'m','description':'Open the world map.'},
            'character':{'kind':'key','value':'c','description':'Open equipment.'}},
            lambda b,a,s:{'status':'service_close_pass' if s=='close' and spec['panel'] not in a['panels'] else
                ('controller_failure' if s!='close' else 'client_or_protocol_failure')},diagnostic_action='close'),'service_close_pass')
    finally:
        if getattr(t,'merchant_restore_required',False):
            raise RuntimeError('merchant inventory cleanup remains pending; preserving the open merchant and NPC restore rows')
        try:
            t.clean_panels()
            if camera_dragged:
                t.io.drag((900,360+camera_drag_y),(900,360))
                t.receipt['camera_drag_fixture']['reversed']=True;t.persist()
            if camera_before is not None:
                from .interaction_camera_fixture import set_zoom
                set_zoom(t,camera_before,'camera_restore')
        finally:fixture.restore()
        state,frame=t.observe('restored')
        t.receipt['restoration']={'frame':frame,'world_position':state['world_position']};t.persist()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--service',choices=SERVICES,required=True);p.add_argument('--point',type=int,nargs=2)
    p.add_argument('--stage-only',action='store_true');commerce=p.add_mutually_exclusive_group()
    p.add_argument('--camera-zoom',type=float,help='temporary camera distance reachable by ordinary wheel steps')
    p.add_argument('--camera-drag-y',type=int,default=0,help='temporary vertical left-mouse camera drag, reversed at cleanup')
    commerce.add_argument('--sell-buyback',action='store_true');commerce.add_argument('--purchase',action='store_true')
    commerce.add_argument('--repair-all',action='store_true');commerce.add_argument('--learn',action='store_true');a=p.parse_args()
    if (a.sell_buyback or a.purchase) and (a.stage_only or a.service!='merchant'):p.error('commerce requires the merchant service')
    if a.repair_all and (a.stage_only or a.service!='repair'):p.error('repair requires the repair service')
    if a.learn and (a.stage_only or a.service!='trainer'):p.error('learning requires the warrior trainer service')
    if a.camera_zoom is not None and not 0<=a.camera_zoom<=30:p.error('camera distance must be between zero and thirty')
    if not -250<=a.camera_drag_y<=250:p.error('camera drag must be within 250 pixels')
    if not a.stage_only and (not a.point or any(not 0<=v<bound for v,bound in zip(a.point,[1280,720]))):p.error('requires a bounded observed NPC point')
    t=Trial(a.output,controller='code' if a.stage_only else 'laya')
    try:suite(t,a.service,a.point,a.stage_only,a.sell_buyback,a.purchase,a.repair_all,a.learn,a.camera_zoom,a.camera_drag_y);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}))
