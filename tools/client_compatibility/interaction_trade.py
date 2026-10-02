"""Trade the existing owned keystone stack out and back through normal UI inputs."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_social import actor
from .interaction_operations import click_case,point
from .interaction_inventory_moves import slot_control
from .interaction_macros import require
from .nearby_fixture import NearbyFixture


def inventory():
    with lab.connection() as con,con.cursor() as cur:
        cur.execute('SELECT ci.guid,ci.bag,ci.slot,ci.item,ii.itemEntry,ii.count,ii.owner_guid '
            'FROM client442_characters.character_inventory ci JOIN client442_characters.item_instance ii ON ci.item=ii.guid '
            'WHERE ci.guid IN (1,2) ORDER BY ci.guid,ci.bag,ci.slot')
        items=cur.fetchall();cur.execute('SELECT guid,money FROM client442_characters.characters WHERE guid IN (1,2) ORDER BY guid')
        return {'items':items,'money':cur.fetchall()}


def original_item(state,guid):
    rows=[r for r in state['items'] if r[3]==guid]
    if len(rows)!=1:raise RuntimeError('owned trade item has no unique native inventory owner')
    return rows[0]


def transfer(trials,sender,recipient,item,case_prefix):
    t,peer=trials[sender],trials[recipient];before=inventory();source=original_item(before,item[3])
    if source[0]!=t.fixture['guid'] or source[6]!=source[0] or source[1]!=0 or not 23<=source[2]<39:
        raise RuntimeError('trade stack must be in the sender backpack')
    slot=source[2]-22
    with actor(sender):
        t.clean_panels();t.execute({'kind':'chat','value':'/targetexact '+peer.fixture['character_name']})
        require(t.step(case_prefix+'.open','Open a trade with '+peer.fixture['character_name']+'.',{
            'trade':{'kind':'chat','value':'/trade','description':'Type /trade to trade with the nearby targeted player.'},
            'inspect':{'kind':'chat','value':'/inspect','description':'Inspect the targeted player.'},
            'map':{'kind':'key','value':'m','description':'Open the map.'}},
            lambda b,a,s:{'status':'trade_open_pass' if s=='trade' and a.get('trade',{}).get('visible') else
                ('controller_failure' if s!='trade' else 'client_or_protocol_failure'),'oracle':{'trade':a.get('trade')}},diagnostic_action='trade'),'trade_open_pass')
        state,_=t.observe(case_prefix+'_offer_fixture')
        if 0 not in state.get('bags',[]):t.execute({'kind':'key','value':'b'})
        state,_=t.observe(case_prefix+'_bag_fixture')
        bag=next((x for x in state.get('bag_items',[]) if x['bag']==0 and x['slot']==slot),None)
        if not bag or (bag['id'],bag['count'])!=(64394,item[5]):raise RuntimeError('visible keystone stack disagrees with the native fixture')
        control=slot_control(t,0,slot)
        if control is None:raise RuntimeError('observed keystone bag button missing')
        require(t.step(case_prefix+'.offer','Offer the entire Dwarf Keystone stack in the trade.',{
            'offer':{'kind':'click','value':point(control),'button':3,'description':'Right-click the visible Dwarf Keystone stack to offer it in the open trade.'},
            'pick':{'kind':'click','value':point(control),'description':'Left-click to pick up the stack on the cursor.'},
            'escape':{'kind':'key','value':'Escape','description':'Cancel the trade.'}},
            lambda b,a,s:{'status':'trade_offer_pass' if s=='offer' and any(x['name']=='Dwarf Keystone' and x['count']==item[5]
                for x in a.get('trade',{}).get('items',[])) else
                ('controller_failure' if s!='offer' else 'client_or_protocol_failure'),'oracle':{'trade':a.get('trade')}},diagnostic_action='offer'),'trade_offer_pass')
    with actor(recipient):
        observed,frame=peer.observe(case_prefix+'_peer_offer')
        visible=observed.get('trade',{}).get('visible') and any(x['name']=='Dwarf Keystone' and x['count']==item[5]
            for x in observed.get('trade',{}).get('target_items',[]))
        peer.receipt.setdefault('peer_offers',[]).append({'id':case_prefix,'visible':visible,'trade':observed.get('trade'),'frame':frame});peer.persist()
        if not visible:raise RuntimeError('recipient did not observe the keystone offer')
    with actor(sender):
        require(click_case(t,case_prefix+'.accept_sender','Accept this keystone trade.',
            lambda c:c['name']=='TradeFrameTradeButton',
            lambda b,a,s:{'status':'trade_accept_pass' if s and any(x['event']=='TRADE_ACCEPT_UPDATE' and x.get('own')==1
                for x in a['trade']['events']) else
                ('controller_failure' if not s else 'client_or_protocol_failure'),'oracle':{'trade':a.get('trade')}}),'trade_accept_pass')
    with actor(recipient):
        def completed(b,a,s):
            now=inventory();native=original_item(now,item[3]);matches=native[0]==peer.fixture['guid'] and native[6]==native[0] and native[4:6]==item[4:6]
            return {'status':'trade_complete_pass' if s and not a['trade']['visible'] and matches else
                ('controller_failure' if not s else 'client_or_protocol_failure'),'oracle':{'native_item':native,'matches':matches,'trade':a.get('trade')}}
        require(click_case(peer,case_prefix+'.accept_recipient','Accept the offered keystones and complete the trade.',
            lambda c:c['name']=='TradeFrameTradeButton',completed),'trade_complete_pass')
        state,_=peer.observe(case_prefix+'_received_bag_fixture')
        if 0 not in state.get('bags',[]):peer.execute({'kind':'key','value':'b'})
        state,frame=peer.observe(case_prefix+'_received_stack')
        native=original_item(inventory(),item[3]);visible=any(x['bag']==0 and x['slot']==native[2]-22 and x['id']==64394 and x['count']==item[5]
            for x in state.get('bag_items',[]))
        peer.receipt.setdefault('received_stacks',[]).append({'id':case_prefix,'native':native,'visible':visible,'frame':frame});peer.persist()
        if not visible:raise RuntimeError('received stack missing from the recipient backpack UI')
    for name in [sender,recipient]:
        with actor(name):trials[name].clean_panels()


def suite(out):
    out.mkdir(parents=True,exist_ok=False,mode=0o700)
    cohort={'started_at':time.time(),'completed':False,'failure':None};trials={};fixture=None;baseline=None;item=None
    try:
        for name in ['primary','scout']:
            with actor(name):
                t=trials[name]=Trial(out/name);actors.session_entry(t.fixture);t.clean_panels()
        lab.server_command('saveall');time.sleep(1);baseline=inventory()
        rows=[r for r in baseline['items'] if r[4]==64394]
        if len(rows)!=1 or rows[0][0]!=1 or rows[0][5]!=5:raise RuntimeError('requires the existing primary five-keystone stack')
        item=rows[0];lab.private_write(out/'inventory_baseline.json',json.dumps(baseline,indent=2)+'\n')
        fixture=NearbyFixture(out,trials['primary'].fixture,trials['scout'].fixture,open_ground=True);fixture.prepare()
        transfer(trials,'primary','scout',item,'trade.outbound')
        transfer(trials,'scout','primary',item,'trade.return')
        if inventory()!=baseline:raise RuntimeError('native inventory/money baseline differs after the round trip')
        cohort['completed']=True
    except Exception as e:cohort['failure']=f'{type(e).__name__}: {e}'
    finally:
        for name,t in trials.items():
            with actor(name):
                try:t.clean_panels()
                except Exception as e:cohort['completed']=False;cohort.setdefault('cleanup_failures',{})[name]=str(e)
        if item:
            try:
                owner=original_item(inventory(),item[3])[0]
                if owner==2:
                    # Restore through the same ordinary trade, with separate code receipts.
                    cleanup={}
                    for name in ['primary','scout']:
                        with actor(name):cleanup[name]=Trial(out/'restore'/name,controller='code')
                    try:
                        transfer(cleanup,'scout','primary',item,'restore.trade')
                        for t in cleanup.values():t.receipt['completed']=True
                    except Exception as e:
                        for t in cleanup.values():t.receipt['failure']=str(e)
                        raise
                    finally:
                        for t in cleanup.values():t.receipt['finished_at']=time.time();t.persist()
                cohort['inventory_restored']=inventory()==baseline
                if not cohort['inventory_restored']:raise RuntimeError('native item/money baseline was not restored')
            except Exception as e:cohort['completed']=False;cohort['inventory_cleanup_failure']=str(e)
        if fixture and cohort.get('inventory_restored',item is None):
            try:fixture.restore()
            except Exception as e:cohort.update(completed=False,cleanup_failure=str(e))
        for name,t in trials.items():
            with actor(name):
                try:
                    s,_=t.observe('cleanup_target')
                    if s.get('target',{}).get('exists'):t.execute({'kind':'key','value':'Escape'})
                    s,f=t.observe('restored');t.receipt['restoration']={'frame':f,'world_position':s['world_position']}
                except Exception as e:cohort['completed']=False;cohort.setdefault('cleanup_failures',{})[name]=str(e)
            t.receipt.update(completed=cohort['completed'],failure=cohort['failure'],finished_at=time.time());t.persist()
        cohort['finished_at']=time.time();lab.private_write(out/'cohort.json',json.dumps(cohort,indent=2)+'\n');print(json.dumps(cohort),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);suite(p.parse_args().output)
