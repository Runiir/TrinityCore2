"""Purchase one existing vendor bundle; separate code fixtures restore inventory/money."""
import time
from . import actors,lab_runtime as lab
from .interaction_trade import inventory
from .interaction_operations import controls,point
from .interaction_macros import require
from .interaction_crafting import fixture_command
from .interaction_fixture_permissions import item_fixture_permission,money_fixture_permission
from .observation.inventory import Inventory


def buy(t):
    oracle=Inventory(lab.ROOT,actors.session_entry(t.fixture)['session'],t.fixture['guid']).poll()
    lab.server_command('saveall');time.sleep(1);baseline=inventory();money=oracle.money()
    state,_=t.observe('purchase_fixture')
    rows=[r for r in state.get('merchant',{}).get('items',[]) if r.get('id')==159]
    if len(rows)!=1 or oracle.count(159) or any(r['id']==159 for r in state.get('bag_items',[])):
        raise RuntimeError('requires one native water catalog bundle and no existing owned water')
    row=rows[0];quantity=row['quantity'];price=row['price']
    if state.get('merchant',{}).get('tab')!=1 or quantity!=5 or not 0<price<=100 or state.get('money')!=money:
        raise RuntimeError('purchase fixture price/quantity/money disagrees')
    control=next((c for c in controls(t) if c['name']=='MerchantItem'+str(row['index'])+'ItemButton'),None)
    if not control:raise RuntimeError('observed catalog item button is absent')
    t.receipt['purchase_baseline']={'inventory':baseline,'money':money,'item_id':159,'quantity':quantity,'price':price};t.persist()
    t.merchant_restore_required=True
    def outcome(b,a,selected):
        oracle.poll();native=oracle.count(159)==quantity and oracle.money()==money-price
        visible=sum(r['count'] for r in a.get('bag_items',[]) if r['id']==159)==quantity and a.get('money')==money-price
        loot=a.get('last_loot') or {};prior=b.get('last_loot') or {}
        notified=loot.get('id')==159 and loot.get('count')==quantity and loot.get('time',0)>prior.get('time',0)
        return {'status':'purchase_pass' if selected=='buy' and native and visible and notified else
            ('controller_failure' if selected!='buy' else 'client_or_protocol_failure'),
            'oracle':{'native_count':oracle.count(159),'visible_money':a.get('money'),'native_money':oracle.money(),
                'expected_quantity':quantity,'expected_money':money-price,'native_matches':native,'visible_matches':visible,
                'notification_matches':notified,'last_loot':loot}}
    try:
        require(t.step('merchant.buy_bundle','Buy one five-item bundle of Refreshing Spring Water.',{
            'buy':{'kind':'click','value':point(control),'button':3,'description':'Right-click the displayed Refreshing Spring Water bundle to buy it.'},
            'pick':{'kind':'click','value':point(control),'description':'Pick up the vendor item on the cursor without buying it.'},
            'escape':{'kind':'key','value':'Escape','description':'Close the merchant window.'}},outcome,diagnostic_action='buy'),'purchase_pass')
    finally:
        oracle.poll();count=oracle.count(159);delta=money-oracle.money()
        if count not in [0,quantity] or delta not in [0,price]:
            raise RuntimeError('unexpected transaction state; preserving the merchant fixture for diagnosis')
        if count or delta:
            fixture_command(t,'/cleartarget','cleanup targets only the owned purchase actor')
            if count:
                with item_fixture_permission(t):fixture_command(t,f'.additem 159 {-count}','remove only the newly purchased disposable water bundle')
            if delta:
                with money_fixture_permission(t):fixture_command(t,f'.modify money {delta}','restore only the observed purchase charge')
        lab.server_command('saveall');time.sleep(1);after=inventory();oracle.poll()
        restored=after==baseline and oracle.count(159)==0 and oracle.money()==money
        t.receipt['purchase_restoration']={'restored':restored,'inventory':after,'native_money':oracle.money()};t.persist()
        if not restored:raise RuntimeError('purchase fixture inventory/money restoration failed')
        t.merchant_restore_required=False
