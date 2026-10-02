"""Bank an existing owned stack and restore it, with independent native slot checks."""
import time
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_trade import inventory
from .interaction_inventory_moves import slot_control
from .interaction_operations import controls,point
from .interaction_macros import require
from .observation.inventory import Inventory


def transfer(t,oracle,item,source,destination,case_id):
    if source[0]==0:control=slot_control(t,*source)
    else:control=next((c for c in controls(t) if c['name']=='BankFrameItem'+str(source[1])),None)
    if not control:raise RuntimeError('observed bank transfer source control is absent')
    def outcome(b,a,s):
        oracle.poll();native=oracle.slot(*destination)==item and oracle.slot(*source)['guid']==0
        rows=a.get('bank',{}).get('items',[]) if destination[0]==-1 else a.get('bag_items',[])
        shown=any(x['slot']==destination[1] and x['id']==item['id'] and x['count']==item['count'] and
            x['bag']==destination[0] for x in rows)
        return {'status':'bank_transfer_pass' if s=='transfer' and native and shown else
            ('controller_failure' if s!='transfer' else 'client_or_protocol_failure'),
            'oracle':{'native_source':oracle.slot(*source),'native_destination':oracle.slot(*destination),
                'native_matches':native,'visible_matches':shown,'bank':a.get('bank')}}
    return t.step(case_id,'Move the entire Draenei Tome stack '+('into your bank.' if destination[0]==-1 else 'back into your backpack.'),{
        'transfer':{'kind':'click','value':point(control),'button':3,
            'description':'Right-click the visible Draenei Tome stack to '+('deposit it into the open bank.' if destination[0]==-1 else 'withdraw it into your backpack.')},
        'pick':{'kind':'click','value':point(control),'description':'Pick up the stack on the cursor without completing a transfer.'},
        'escape':{'kind':'key','value':'Escape','description':'Close the bank.'}},outcome,diagnostic_action='transfer')


def roundtrip(t,npc_point):
    from .interaction_bank import open_bank
    oracle=Inventory(lab.ROOT,actors.session_entry(t.fixture)['session'],t.fixture['guid']).poll()
    lab.server_command('saveall');time.sleep(1);baseline=inventory()
    state,_=t.observe('bank_stack_fixture')
    if 0 not in state.get('bags',[]):t.execute({'kind':'key','value':'b'})
    state,_=t.observe('bank_stack_bags')
    candidates=[x for x in state.get('bag_items',[]) if x['bag']==0 and x['id']==64394 and x['count']==5]
    if len(candidates)!=1 or any(oracle.slot(-1,s)['guid'] for s in range(1,29)):
        raise RuntimeError('requires the existing five-item Tome stack and an empty base bank')
    source=(0,candidates[0]['slot']);destination=(-1,1);item=oracle.slot(*source)
    if item['id']!=64394 or item['count']!=5:raise RuntimeError('native stack disagrees with the visible fixture')
    t.bank_restore_required=True;t.receipt['bank_inventory_baseline']={'inventory':baseline,'source':source,'destination':destination,'item':item};t.persist()
    try:
        require(transfer(t,oracle,item,source,destination,'bank.deposit_existing_stack'),'bank_transfer_pass')
        require(transfer(t,oracle,item,destination,source,'bank.withdraw_existing_stack'),'bank_transfer_pass')
    finally:
        oracle.poll()
        if oracle.slot(*destination)==item:
            cleanup=Trial(t.out/'bank_restore',controller='code')
            try:
                state,_=cleanup.observe('restore_fixture')
                if 'BankFrame' not in state['panels']:
                    cleanup.clean_panels();open_bank(cleanup,npc_point)
                state,_=cleanup.observe('restore_bags')
                if 0 not in state.get('bags',[]):cleanup.execute({'kind':'key','value':'b'})
                require(transfer(cleanup,oracle,item,destination,source,'restore.bank_withdraw'),'bank_transfer_pass')
                cleanup.receipt['completed']=True
            except Exception as e:cleanup.receipt['failure']=str(e);raise
            finally:cleanup.receipt['finished_at']=time.time();cleanup.persist()
        lab.server_command('saveall');time.sleep(1);after=inventory()
        restored=after==baseline and oracle.poll().slot(*source)==item and not oracle.slot(*destination)['guid']
        t.receipt['bank_inventory_restoration']={'restored':restored,'inventory':after};t.persist()
        if not restored:raise RuntimeError('bank stack/inventory/money baseline was not restored; preserving NPC fixture')
        t.bank_restore_required=False
