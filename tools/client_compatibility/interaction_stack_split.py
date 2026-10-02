"""Split one existing item, place it, then merge it back through physical UI."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_operations import point,click_case
from .interaction_inventory_moves import slot_control
from .interaction_macros import require
from .observation.inventory import Inventory


def counts_match(state,source,destination,original,split):
    rows={(x['bag'],x['slot']):x for x in state.get('bag_items',[])}
    left=rows.get(source,{})
    if left.get('id')!=original['id'] or left.get('count')!=original['count']-(1 if split else 0):return False
    right=rows.get(destination,{})
    return right.get('id')==original['id'] and right.get('count')==1 if split else destination not in rows


def merge(trial,native,source,destination,original):
    src,dst=slot_control(trial,*destination),slot_control(trial,*source)
    if src is None or dst is None:raise RuntimeError('observed merge slots are absent')
    def oracle(b,a,s):
        native.poll();matches=native.slot(*source)==original and not native.slot(*destination)['guid']
        visible=counts_match(a,source,destination,original,False)
        return {'status':'inventory_merge_pass' if matches and visible else ('controller_failure' if s!='drag' else 'client_or_protocol_failure'),
            'oracle':{'native_matches':matches,'visible_matches':visible,'native_source':native.slot(*source),'native_destination':native.slot(*destination)}}
    return trial.step('bags.merge_stack','Merge the split item back into its original stack.',{
        'drag':{'kind':'drag','start':point(src),'end':point(dst),'description':'Drag the one-item split stack onto the original stack to merge them.'},
        'escape':{'kind':'key','value':'Escape','description':'Close bags.'},
        'click':{'kind':'click','value':point(src),'description':'Pick up the split stack without placing it.'}},oracle,diagnostic_action='drag')


def suite(trial):
    native=Inventory(lab.ROOT,actors.session_entry(trial.fixture)['session'],trial.fixture['guid']).poll()
    trial.clean_panels();trial.execute({'kind':'key','value':'b'});state,_=trial.observe('split_fixture')
    candidates=[x for x in state.get('bag_items',[]) if x['bag']==0 and x['count']>1 and not x['locked']]
    empty=[s for s in range(1,17) if not native.slot(0,s)['guid']]
    if not candidates or not empty:raise RuntimeError('split fixture needs an existing stack and an empty backpack slot')
    source=(0,candidates[0]['slot']);destination=(0,empty[-1]);original=native.slot(*source)
    trial.receipt['fixture_setup']={'source':'code_ordinary_input','input':'b','purpose':'open existing stack fixture'}
    trial.receipt['stack_baseline']={'source':source,'destination':destination,'original':original};trial.persist()
    try:
        control=slot_control(trial,*source)
        if control is None:raise RuntimeError('observed source stack is absent')
        require(trial.step('bags.split_dialog','Open the stack-splitting dialog for this stack.',{
            'split':{'kind':'click','value':point(control),'modifiers':['shift'],'description':'Shift-left-click the visible stack to split it.'},
            'click':{'kind':'click','value':point(control),'description':'Left-click to pick up the entire stack.'},
            'escape':{'kind':'key','value':'Escape','description':'Close bags.'}},
            lambda b,a,s:{'status':'panel_open_pass' if 'StackSplitFrame' in a['panels'] else ('controller_failure' if s!='split' else 'client_or_protocol_failure')},
            diagnostic_action='split'),'panel_open_pass')
        require(click_case(trial,'bags.confirm_split','Confirm the one-item split.',lambda c:c['text']=='Okay',
            lambda b,a,s:{'status':'split_cursor_pass' if a.get('item_cursor') and 'StackSplitFrame' not in a['panels'] else
                ('controller_failure' if not s else 'client_or_protocol_failure')}),'split_cursor_pass')
        target=slot_control(trial,*destination)
        if target is None:raise RuntimeError('observed destination slot is absent')
        def oracle(b,a,s):
            native.poll();left,right=native.slot(*source),native.slot(*destination)
            matches=left['guid']==original['guid'] and left['count']==original['count']-1 and right['id']==original['id'] and right['count']==1 and right['guid']!=original['guid']
            visible=counts_match(a,source,destination,original,True)
            return {'status':'inventory_split_pass' if matches and visible else ('controller_failure' if s!='place' else 'client_or_protocol_failure'),
                'oracle':{'native_matches':matches,'visible_matches':visible,'native_source':left,'native_destination':right}}
        require(trial.step('bags.split_stack','Place the one-item split in the empty backpack slot.',{
            'place':{'kind':'click','value':point(target),'description':'Left-click the empty backpack slot to place the one-item split.'},
            'escape':{'kind':'key','value':'Escape','description':'Cancel the item cursor.'},
            'character':{'kind':'key','value':'c','description':'Open character equipment.'}},oracle,diagnostic_action='place'),'inventory_split_pass')
        require(merge(trial,native,source,destination,original),'inventory_merge_pass')
    finally:
        trial.io.key('Escape');native.poll()
        if native.slot(*destination)['guid'] and native.slot(*destination)['id']==original['id']:
            cleanup=Trial(trial.out/'restore',controller='code')
            try:
                cleanup.clean_panels();cleanup.execute({'kind':'key','value':'b'})
                require(merge(cleanup,native,source,destination,original),'inventory_merge_pass');cleanup.receipt['completed']=True
            except Exception as e:cleanup.receipt['failure']=str(e);raise
            finally:cleanup.receipt['finished_at']=time.time();cleanup.persist()
        trial.clean_panels()
        if native.poll().slot(*source)!=original or native.slot(*destination)['guid']:raise RuntimeError('split baseline was not restored')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();t=Trial(a.output)
    try:suite(t);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}))


if __name__=='__main__':main()
