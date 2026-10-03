"""Unequip and re-equip a real item, checking UI slots and native effective stats."""
import argparse,json,math,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_operations import controls,point
from .interaction_inventory_moves import slot_control
from .interaction_macros import require
from .observation.inventory import Inventory


def stats_check(trial,oracle,label):
    state,frame=trial.observe(label);native=oracle.poll().character_stats();stats=state.get('player_stats',{})
    visible={k:(stats.get(k) or [None,None])[1] for k in ['strength','armor']}
    visible.update(health=stats.get('health'),damage=(stats.get('damage') or [])[:2])
    scalar=all(visible[k]==native[k] for k in ['strength','armor','health'])
    damage=len(visible['damage'])==2 and all(math.isclose(a,b,rel_tol=1e-5,abs_tol=.02) for a,b in zip(visible['damage'],native['damage']))
    row={'id':'character.stats.'+label,'time':time.time(),'status':'character_stats_pass' if scalar and damage else 'character_stats_failure',
        'selection_source':'read_only_native_and_addon_oracle','oracle':{'native':native,'visible':visible,'scalar_match':scalar,'damage_match':damage},'frame':frame}
    trial.receipt['cases'].append(row);trial.persist();print(json.dumps(row),flush=True)
    return scalar and damage


def change(trial,oracle,item,destination,equip=False,equipment_slot=1,equipment_control='CharacterHeadSlot',case_suffix=''):
    if not 1<=equipment_slot<=19:raise ValueError('equipment slot outside the native range')
    rows=controls(trial);head=next((c for c in rows if c['name']==equipment_control),None)
    bag=slot_control(trial,*destination)
    if head is None or bag is None:raise RuntimeError('visible equipment and bag controls required')
    actions={'change':({'kind':'click','value':point(bag),'button':3,
        'description':'Right-click the equipment item in the backpack to equip it.'} if equip else
        {'kind':'drag','start':point(head),'end':point(bag),'description':'Drag the equipped item into the indicated empty backpack slot.'}),
        'escape':{'kind':'key','value':'Escape','description':'Close the equipment window.'},
        'map':{'kind':'key','value':'m','description':'Open the world map.'}}
    def visible_outcome(a):
        equipped=(a.get('equipment') or [None]*19)[equipment_slot-1]==(item['id'] if equip else 0)
        shown=next((x for x in a.get('bag_items',[]) if (x['bag'],x['slot'])==destination),None)
        return equipped and (shown is None if equip else shown is not None and shown['id']==item['id'] and shown['count']==item['count'])
    def outcome(b,a,s):
        oracle.poll();actual=oracle.equipment(equipment_slot);stored=oracle.slot(*destination)
        expected=actual==item and stored['guid']==0 if equip else actual['guid']==0 and stored==item
        visible=visible_outcome(a)
        return {'status':'equipment_change_pass' if expected and visible else ('controller_failure' if s!='change' else 'client_or_protocol_failure'),
            'oracle':{'native_equipment':actual,'equipment_slot':equipment_slot,'equipment_control':equipment_control,
                **({'native_head':actual} if equipment_slot==1 else {}),
                'native_bag':stored,'native_matches':expected,'visible_matches':visible}}
    return trial.step(('character.equip' if equip else 'character.unequip')+case_suffix,
        'Equip the item from the backpack.' if equip else 'Unequip the item into the empty backpack slot.',
        actions,outcome,diagnostic_action='change',await_state=visible_outcome)


def open_panels(trial):
    trial.clean_panels()
    for key in ['c','b']:trial.execute({'kind':'key','value':key})
    trial.receipt['fixture_inputs']=[{'source':'code_fixture','kind':'key','value':key} for key in ['c','b']];trial.persist()


def suite(trial):
    oracle=Inventory(lab.ROOT,actors.session_entry(trial.fixture)['session'],trial.fixture['guid']).poll()
    item=oracle.equipment(1);empty=[s for s in range(1,17) if not oracle.slot(0,s)['guid']]
    if not item['guid'] or not empty:raise RuntimeError('equipped helmet and empty backpack slot required')
    destination=(0,empty[-1]);trial.receipt['equipment_baseline']={'item':item,'destination':destination,'native_stats':oracle.character_stats()};trial.persist()
    checks=[]
    try:
        open_panels(trial);checks.append(stats_check(trial,oracle,'equipped_before'))
        require(change(trial,oracle,item,destination),'equipment_change_pass')
        checks.append(stats_check(trial,oracle,'unequipped'))
        require(change(trial,oracle,item,destination,True),'equipment_change_pass')
        checks.append(stats_check(trial,oracle,'equipped_after'))
    finally:
        oracle.poll()
        if oracle.equipment(1)['guid']==0 and oracle.slot(*destination)==item:
            cleanup=Trial(trial.out/'restore',controller='code')
            try:
                open_panels(cleanup);require(change(cleanup,oracle,item,destination,True),'equipment_change_pass');cleanup.receipt['completed']=True
            except Exception as e:cleanup.receipt['failure']=str(e);raise
            finally:cleanup.receipt['finished_at']=time.time();cleanup.persist()
        trial.clean_panels()
        if oracle.poll().equipment(1)!=item or oracle.slot(*destination)['guid']:raise RuntimeError('equipment baseline restoration failed')
    if not all(checks):raise RuntimeError('client character stats differ from native effective stats')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();trial=Trial(a.output)
    try:suite(trial);trial.receipt['completed']=True
    except Exception as e:trial.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:trial.receipt['finished_at']=time.time();trial.persist();print(json.dumps({'completed':trial.receipt['completed'],'failure':trial.receipt['failure']}))


if __name__=='__main__':main()
