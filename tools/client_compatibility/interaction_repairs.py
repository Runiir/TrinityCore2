"""Repair pre-existing owned wear; retain repaired gear and restore experiment money."""
import time
from . import actors,lab_runtime as lab
from .interaction_trade import inventory
from .interaction_operations import click_case
from .interaction_macros import require
from .interaction_crafting import fixture_command
from .interaction_fixture_permissions import money_fixture_permission
from .observation.inventory import Inventory
from .world.objects import INDEX


def durability(oracle,baseline):
    result={}
    for row in baseline['items']:
        if row[0]!=oracle.guid:continue
        guid=(0x4000<<48)|row[3];fields=oracle.objects.get(guid,{})
        maximum=fields.get(INDEX['ITEM_FIELD_MAXDURABILITY'],0)
        if maximum:result[str(guid)]={'current':fields.get(INDEX['ITEM_FIELD_DURABILITY'],0),'maximum':maximum}
    return result


def repair_all(t):
    oracle=Inventory(lab.ROOT,actors.session_entry(t.fixture)['session'],t.fixture['guid']).poll()
    lab.server_command('saveall');time.sleep(1);baseline=inventory();money=oracle.money()
    state,_=t.observe('repair_fixture');merchant=state.get('merchant',{});price=merchant.get('repair_cost')
    before=durability(oracle,baseline);damaged=[guid for guid,row in before.items() if row['current']<row['maximum']]
    if not merchant.get('repairable') or not merchant.get('repair_needed') or not price or not 0<price<money or not damaged:
        raise RuntimeError('requires existing native wear, visible repair service and an affordable positive quote')
    if state.get('money')!=money:raise RuntimeError('visible/native fixture money differs')
    t.receipt['repair_baseline']={'inventory':baseline,'money':money,'quoted_cost':price,'durability':before,
        'damaged_guids':damaged,'retained_change':'repair existing wear to full durability; do not introduce replacement damage'};t.persist()
    t.merchant_restore_required=True
    def outcome(b,a,s):
        oracle.poll();after=durability(oracle,baseline)
        repaired=all(after.get(guid,{}).get('current')==before[guid]['maximum'] for guid in damaged)
        visible=a.get('merchant',{}).get('repair_cost')==0 and not a.get('merchant',{}).get('repair_needed')
        money_matches=oracle.money()==money-price and a.get('money')==money-price
        return {'status':'repair_all_pass' if s and repaired and visible and money_matches else
            ('controller_failure' if not s else 'client_or_protocol_failure'),
            'oracle':{'all_native_wear_repaired':repaired,'visible_repair_complete':visible,'quoted_cost':price,
                'native_money':oracle.money(),'visible_money':a.get('money'),'money_matches':money_matches,'durability':after}}
    try:
        require(click_case(t,'merchant.repair_all','Repair all damaged equipment using your own money.',
            lambda c:c['name']=='MerchantRepairAllButton',outcome),'repair_all_pass')
    finally:
        oracle.poll();delta=money-oracle.money()
        if delta<0 or delta>max(price*2,10000):raise RuntimeError('unexpected repair charge; preserving the fixture for diagnosis')
        if delta:
            fixture_command(t,'/cleartarget','restore the repair charge only on the owned actor')
            with money_fixture_permission(t):fixture_command(t,f'.modify money {delta}','restore only the observed repair charge')
        lab.server_command('saveall');time.sleep(1);after=inventory();oracle.poll()
        restored=after==baseline and oracle.money()==money
        t.receipt['repair_restoration']={'inventory_money_restored':restored,'native_money':oracle.money(),
            'retained_durability':durability(oracle,baseline),'restored_charge':delta};t.persist()
        if not restored:raise RuntimeError('repair inventory/money fixture restoration failed')
        t.merchant_restore_required=False
