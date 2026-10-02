"""Move an existing backpack item and restore it using observed physical slots."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_operations import controls,point
from .interaction_macros import require
from .observation.inventory import Inventory


def slot_control(trial,bag,slot):
    return next((c for c in controls(trial) if c.get('bag_id')==bag and c.get('bag_slot')==slot and c['kind']=='Button'),None)


def move(trial,oracle,source,destination,item,case_id):
    before,after=slot_control(trial,*source),slot_control(trial,*destination)
    if before is None or after is None:raise RuntimeError('observed bag-slot controls are absent')
    def outcome(b,a,s):
        oracle.poll();src,dst=oracle.slot(*source),oracle.slot(*destination)
        shown={(x['bag'],x['slot']):x for x in a.get('bag_items',[])}
        visible=source not in shown and shown.get(destination,{}).get('id')==item['id'] and shown[destination]['count']==item['count']
        native=src['guid']==0 and dst==item
        return {'status':'inventory_move_pass' if visible and native else ('controller_failure' if s!='drag' else 'client_or_protocol_failure'),
            'oracle':{'native_source':src,'native_destination':dst,'visible_matches':visible,'native_matches':native}}
    return trial.step(case_id,'Move the indicated item into the indicated empty bag slot.',{
        'drag':{'kind':'drag','start':point(before),'end':point(after),
            'description':f'Drag the item in bag {source[0]}, slot {source[1]} to empty bag {destination[0]}, slot {destination[1]}.'},
        'escape':{'kind':'key','value':'Escape','description':'Close the bag panels.'},
        'click':{'kind':'click','value':point(before),'description':'Pick up the item without placing it into another slot.'}},outcome,diagnostic_action='drag')


def suite(trial):
    session=actors.session_entry(trial.fixture)['session'];oracle=Inventory(lab.ROOT,session,trial.fixture['guid']).poll()
    trial.clean_panels()
    require(trial.step('bags.backpack','Open the backpack.',{
        'bag':{'kind':'key','value':'b','description':'Press B to open bags.'},
        'character':{'kind':'key','value':'c','description':'Press C to open equipment.'},
        'map':{'kind':'key','value':'m','description':'Press M to open the world map.'}},
        lambda b,a,s:{'status':'panel_open_pass' if a.get('bags') else 'controller_failure'},diagnostic_action='bag'),'panel_open_pass')
    state,_=trial.observe('inventory_fixture')
    occupied=[x for x in state.get('bag_items',[]) if x['bag']==0 and not x['locked']]
    empty=[slot for slot in range(1,17) if not oracle.slot(0,slot)['guid']]
    if not occupied or not empty:raise RuntimeError('backpack requires an existing unlocked item and an empty slot')
    source=(0,occupied[0]['slot']);destination=(0,empty[-1]);item=oracle.slot(*source)
    if item['id']!=occupied[0]['id'] or item['count']!=occupied[0]['count']:raise RuntimeError('native and visible inventory fixture disagree')
    trial.receipt['inventory_baseline']={'source':source,'destination':destination,'item':item};trial.persist()
    try:
        require(move(trial,oracle,source,destination,item,'bags.move_item'),'inventory_move_pass')
        require(move(trial,oracle,destination,source,item,'bags.move_item_restore'),'inventory_move_pass')
    finally:
        trial.io.key('Escape');oracle.poll()
        if oracle.slot(*destination)==item and oracle.slot(*source)['guid']==0:
            # Cleanup is ordinary input and explicitly separated from model qualification.
            cleanup=Trial(trial.out/'restore',controller='code')
            try:
                cleanup.io.key('b');require(move(cleanup,oracle,destination,source,item,'bags.restore_baseline'),'inventory_move_pass')
                cleanup.receipt['completed']=True
            except Exception as e:cleanup.receipt['failure']=str(e);raise
            finally:cleanup.receipt['finished_at']=time.time();cleanup.persist()
        trial.clean_panels()
        if oracle.poll().slot(*source)!=item or oracle.slot(*destination)['guid']:
            raise RuntimeError('inventory baseline restoration failed')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--suite',choices=['backpack','cross_bag'],default='backpack');a=p.parse_args();t=Trial(a.output)
    try:(suite if a.suite=='backpack' else cross_bag_suite)(t);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}))


def cross_bag_suite(trial):
    oracle=Inventory(lab.ROOT,actors.session_entry(trial.fixture)['session'],trial.fixture['guid']).poll()
    trial.clean_panels()
    require(trial.step('bags.open_all','Open every equipped bag.',{
        'all':{'kind':'key','value':'shift+b','description':'Press Shift-B to open all equipped bags.'},
        'backpack':{'kind':'key','value':'b','description':'Press B to open only the backpack.'},
        'character':{'kind':'key','value':'c','description':'Open equipment.'}},
        lambda b,a,s:{'status':'panel_open_pass' if set(a.get('bags',[]))=={0,1,2,3,4} else 'controller_failure'},diagnostic_action='all'),'panel_open_pass')
    state,_=trial.observe('cross_bag_fixture')
    occupied=[x for x in state.get('bag_items',[]) if x['bag']==0 and not x['locked']]
    empty=[s for s in range(1,state['bag_slots'][1]+1) if not oracle.slot(1,s)['guid']]
    if not occupied or not empty:raise RuntimeError('cross-bag fixture needs an existing backpack item and empty equipped-bag slot')
    source=(0,occupied[0]['slot']);destination=(1,empty[-1]);item=oracle.slot(*source)
    trial.receipt['inventory_baseline']={'source':source,'destination':destination,'item':item};trial.persist()
    try:
        require(move(trial,oracle,source,destination,item,'bags.move_to_equipped_bag'),'inventory_move_pass')
        require(move(trial,oracle,destination,source,item,'bags.move_from_equipped_bag'),'inventory_move_pass')
    finally:
        trial.io.key('Escape');oracle.poll()
        if oracle.slot(*destination)==item and oracle.slot(*source)['guid']==0:
            cleanup=Trial(trial.out/'restore',controller='code')
            try:
                cleanup.clean_panels();cleanup.execute({'kind':'key','value':'shift+b'})
                require(move(cleanup,oracle,destination,source,item,'bags.restore_cross_bag_baseline'),'inventory_move_pass');cleanup.receipt['completed']=True
            except Exception as e:cleanup.receipt['failure']=str(e);raise
            finally:cleanup.receipt['finished_at']=time.time();cleanup.persist()
        trial.clean_panels()
        if oracle.poll().slot(*source)!=item or oracle.slot(*destination)['guid']:raise RuntimeError('cross-bag baseline restoration failed')


if __name__=='__main__':main()
