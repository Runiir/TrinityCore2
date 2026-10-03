"""Bounded parallel UI control on a private actor display; no gameplay mutation."""
import argparse,json,time
from pathlib import Path
from . import actors
from .interaction_trial import Trial
from .interaction_macros import require


def suite(t):
    actors.session_entry(t.fixture);t.clean_panels()
    state,frame=t.observe('isolated_baseline')
    baseline={k:state.get(k) for k in ['guid','money','equipment','group','raid_profile']}
    t.receipt['baseline']={'state':state,'frame':frame};t.persist()
    try:
        for case,key,panel,goal in [('bags','b',None,'Open the backpack.'),
                ('character','c','CharacterFrame','Open character equipment.'),
                ('friends','o','FriendsFrame','Open the friends window.')]:
            t.clean_panels()
            options={
                'bag':{'kind':'key','value':'b','description':'Press B to open the backpack.'},
                'character':{'kind':'key','value':'c','description':'Press C to open character equipment.'},
                'friends':{'kind':'key','value':'o','description':'Press O to open the friends window.'},
                'escape':{'kind':'key','value':'Escape','description':'Close the current window or open the game menu.'}}
            selected={'b':'bag','c':'character','o':'friends'}[key]
            require(t.step('isolation.'+case,goal,options,
                lambda b,a,s,panel=panel:{'status':'isolated_ui_pass' if
                    (panel in a.get('panels',[]) if panel else 0 in a.get('bags',[])) else 'controller_or_client_failure',
                    'oracle':{'panels':a.get('panels'),'bags':a.get('bags'),'private_display':True}},
                diagnostic_action=selected),'isolated_ui_pass')
    finally:
        t.clean_panels();after,frame=t.observe('isolated_restored')
        t.receipt['restoration']={'resources_equipment_group_unchanged':all(after.get(k)==v for k,v in baseline.items()),
            'panels_closed':not after.get('panels') and not after.get('bags'),'frame':frame};t.persist()
        if not t.receipt['restoration']['resources_equipment_group_unchanged'] or not t.receipt['restoration']['panels_closed']:
            raise RuntimeError('isolated UI probe changed its actor baseline')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--controller',choices=['code','laya'],default='code');a=p.parse_args()
    t=Trial(a.output,controller=a.controller)
    try:suite(t);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:
        t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
