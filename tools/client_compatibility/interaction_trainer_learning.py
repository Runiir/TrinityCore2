"""Learn the existing available Parry service and restore experiment money."""
import time
from . import actors,lab_runtime as lab
from .interaction_trade import inventory
from .interaction_operations import click_case
from .interaction_macros import require
from .interaction_crafting import fixture_command
from .interaction_fixture_permissions import money_fixture_permission
from .observation.inventory import Inventory

SPELL=3127


def learned(t):
    lab.server_command('saveall');time.sleep(1)
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT active,disabled FROM client442_characters.character_spell WHERE guid=%s AND spell=%s',(t.fixture['guid'],SPELL))
        return q.fetchone()


def learn_selected(t):
    session=actors.session_entry(t.fixture)['session'];oracle=Inventory(lab.ROOT,session,t.fixture['guid']).poll()
    state,_=t.observe('trainer_learning_fixture');service=state.get('trainer',{}).get('service',{})
    price=service.get('cost');probe=state.get('trainer_probe',{});before=learned(t);baseline=inventory();money=oracle.money()
    if before is not None or not probe.get('available') or probe.get('known') is not False:
        raise RuntimeError('requires an existing unlearned native/client Parry fixture')
    if service.get('name')!='Parry' or service.get('state')!='available' or not price or not 0<price<money or state.get('money')!=money:
        raise RuntimeError('requires affordable selected available Parry in the normal trainer window')
    t.receipt['trainer_learning_baseline']={'spell':SPELL,'native':before,'visible':probe,'selected_service':service,
        'money':money,'inventory':baseline,'retained_change':'learn Parry on the owned level-85 warrior'};t.persist()
    t.merchant_restore_required=True
    def outcome(b,a,s):
        native=learned(t);oracle.poll();visible=a.get('trainer_probe',{})
        passed=native==(1,0) and visible.get('known') is True and oracle.money()==money-price and a.get('money')==money-price
        return {'status':'trainer_learning_pass' if s and passed else ('controller_failure' if not s else 'client_or_protocol_failure'),
            'oracle':{'spell':SPELL,'native':native,'visible':visible,'quoted_cost':price,'native_money':oracle.money(),'visible_money':a.get('money')}}
    try:
        require(click_case(t,'trainer.learn','Train the selected available Parry ability.',
            lambda c:c['name']=='ClassTrainerTrainButton',outcome),'trainer_learning_pass')
    finally:
        oracle.poll();delta=money-oracle.money()
        if delta not in (0,price):raise RuntimeError('unexpected trainer charge; preserving the fixture')
        if delta:
            fixture_command(t,'/cleartarget','restore the training charge only on the owned actor')
            with money_fixture_permission(t):fixture_command(t,f'.modify money {delta}','restore only the observed training charge')
        lab.server_command('saveall');time.sleep(1);after=inventory();oracle.poll()
        restored=after==baseline and oracle.money()==money
        t.receipt['trainer_learning_restoration']={'inventory_money_restored':restored,'restored_charge':delta,
            'native_money':oracle.money(),'retained_spell':learned(t)};t.persist()
        if not restored:raise RuntimeError('trainer inventory/money restoration failed')
        t.merchant_restore_required=False
