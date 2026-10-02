"""Sell and buy back existing spare pants using visible inputs and native oracles."""
import time
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_trade import inventory
from .interaction_inventory_moves import slot_control
from .interaction_operations import click_case,point
from .interaction_macros import require
from .observation.inventory import Inventory


def buyback(t,oracle,item,source,money,case_prefix):
    state,_=t.observe(case_prefix+'_tab_fixture')
    if state.get('merchant',{}).get('tab')!=2:
        require(click_case(t,case_prefix+'.tab','Show the merchant buyback list.',
            lambda c:c['name']=='MerchantFrameTab2',
            lambda b,a,s:{'status':'buyback_tab_pass' if s and a.get('merchant',{}).get('tab')==2 else
                ('controller_failure' if not s else 'client_or_protocol_failure')}),'buyback_tab_pass')
    state,frame=t.observe(case_prefix+'_list')
    rows=[r for r in state.get('merchant',{}).get('buyback',[]) if r.get('id')==item['id'] and r.get('count')==item['count']]
    t.receipt.setdefault('buyback_lists',[]).append({'id':case_prefix,'merchant':state.get('merchant'),'frame':frame});t.persist()
    if len(rows)!=1:raise RuntimeError('sold pants are absent or ambiguous in the observed buyback list')
    index=rows[0]['index']
    def outcome(b,a,selected):
        oracle.poll();native=oracle.slot(*source)==item and oracle.money()==money
        visible=a.get('money')==money and any(r['bag']==source[0] and r['slot']==source[1] and
            r['id']==item['id'] and r['count']==item['count'] for r in a.get('bag_items',[]))
        return {'status':'buyback_pass' if selected and native and visible else
            ('controller_failure' if not selected else 'client_or_protocol_failure'),
            'oracle':{'native_item':oracle.slot(*source),'native_money':oracle.money(),'visible_money':a.get('money'),
                'native_matches':native,'visible_matches':visible,'merchant':a.get('merchant')}}
    require(click_case(t,case_prefix+'.item','Buy back your sold spare pants.',
        lambda c:c['name']=='MerchantItem'+str(index)+'ItemButton',outcome),'buyback_pass')


def roundtrip(t):
    oracle=Inventory(lab.ROOT,actors.session_entry(t.fixture)['session'],t.fixture['guid']).poll()
    lab.server_command('saveall');time.sleep(1);baseline=inventory()
    state,_=t.observe('sale_fixture')
    if 0 not in state.get('bags',[]):t.execute({'kind':'key','value':'b'})
    state,_=t.observe('sale_bag_fixture')
    candidates=[r for r in state.get('bag_items',[]) if r['bag']==0 and r['id']==39 and r['count']==1]
    if len(candidates)!=1 or state.get('merchant',{}).get('buyback_count')!=0:
        raise RuntimeError('requires the existing spare pants and an empty buyback list')
    source=(0,candidates[0]['slot']);item=oracle.slot(*source);money=oracle.money()
    if item['id']!=39 or item['count']!=1 or money!=state.get('money'):
        raise RuntimeError('native inventory/money disagrees with the visible sale fixture')
    t.merchant_restore_required=True
    t.receipt['merchant_inventory_baseline']={'inventory':baseline,'source':source,'item':item,'money':money};t.persist()
    control=slot_control(t,*source)
    if not control:raise RuntimeError('observed sale item button is absent')
    def sold(b,a,selected):
        oracle.poll();native=not oracle.slot(*source)['guid'] and oracle.money()>money
        visible=(not any(r['bag']==source[0] and r['slot']==source[1] for r in a.get('bag_items',[])) and
            a.get('money')==oracle.money() and a.get('merchant',{}).get('buyback_count')==1)
        return {'status':'sale_pass' if selected=='sell' and native and visible else
            ('controller_failure' if selected!='sell' else 'client_or_protocol_failure'),
            'oracle':{'native_item':oracle.slot(*source),'native_money':oracle.money(),'visible_money':a.get('money'),
                'money_delta':oracle.money()-money,'native_matches':native,'visible_matches':visible,'merchant':a.get('merchant')}}
    try:
        require(t.step('merchant.sell_existing_pants','Sell your spare pants to the open merchant.',{
            'sell':{'kind':'click','value':point(control),'button':3,'description':'Right-click the spare pants in your backpack to sell them to the merchant.'},
            'pick':{'kind':'click','value':point(control),'description':'Pick up the spare pants on the cursor.'},
            'escape':{'kind':'key','value':'Escape','description':'Close the merchant window.'}},sold,diagnostic_action='sell'),'sale_pass')
        buyback(t,oracle,item,source,money,'merchant.buyback')
    finally:
        oracle.poll()
        if oracle.slot(*source)!=item:
            cleanup=Trial(t.out/'merchant_restore',controller='code')
            try:
                buyback(cleanup,oracle,item,source,money,'restore.buyback');cleanup.receipt['completed']=True
            except Exception as e:cleanup.receipt['failure']=str(e);raise
            finally:cleanup.receipt['finished_at']=time.time();cleanup.persist()
        lab.server_command('saveall');time.sleep(1);after=inventory()
        restored=after==baseline and oracle.poll().slot(*source)==item and oracle.money()==money
        t.receipt['merchant_inventory_restoration']={'restored':restored,'inventory':after};t.persist()
        if not restored:raise RuntimeError('merchant inventory/money baseline was not restored')
        t.merchant_restore_required=False
