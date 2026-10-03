"""Probe stock auction selling with an existing unbound item and native checks."""
import argparse
import json
from pathlib import Path
import time
from . import actors
from .interaction_trial import Trial
from .interaction_auction import auction_state,open_auction
from .interaction_operations import controls,click_case,point
from .interaction_inventory_moves import slot_control
from .interaction_macros import require
from .npc_fixture import NpcFixture


def suite(t,npc_point):
    actors.session_entry(t.fixture);t.clean_panels()
    baseline=auction_state();fixture=NpcFixture(t.out,t.fixture,8719,2097152)
    items=[r for r in baseline['inventory']['items'] if r[0]==1 and r[3]==4]
    if len(items)!=1 or tuple(items[0])!=(1,0,30,4,39,1,1) or baseline['auctions']:
        raise RuntimeError('requires the existing unbound pants in backpack slot 8 and an empty native auction house')
    t.receipt['auction_baseline']=baseline;t.persist()
    try:
        fixture.prepare();t.execute({'kind':'chat','value':'/targetexact '+fixture.npc[2]})
        state,frame=t.observe('auctioneer_staged');t.receipt['staging']={'state':state,'frame':frame};t.persist()
        if state['target'].get('name')!=fixture.npc[2] or not state['target'].get('visible'):
            raise RuntimeError('auctioneer is not visibly targeted')
        open_auction(t,npc_point,fixture.npc[2])
        require(click_case(t,'auction.sell_tab','Open the Sell tab.',lambda c:c['name']=='AuctionHouseFrameSellTab',
            lambda b,a,s:{'status':'auction_sell_tab_pass' if s and a.get('auction',{}).get('tab')==2 else
                ('controller_failure' if not s else 'client_or_protocol_failure')}),'auction_sell_tab_pass')
        state,_=t.observe('sell_fixture')
        if 0 not in state.get('bags',[]):t.execute({'kind':'key','value':'b'})
        state,_=t.observe('sell_bag_fixture')
        bag=next((r for r in state.get('bag_items',[]) if r['bag']==0 and r['slot']==8),None)
        if not bag or (bag['id'],bag['count'],bag['locked'])!=(39,1,False):
            raise RuntimeError('visible sale item disagrees with the native inventory')
        control=slot_control(t,0,8)
        if not control:raise RuntimeError('observed sale item control is absent')
        def outcome(b,a,s):
            sell=a.get('auction',{}).get('sell',{})
            shown=sell.get('id')==39 and sell.get('quantity')==1 and (sell.get('bag'),sell.get('slot'))==(0,8)
            unchanged=auction_state()==baseline
            return {'status':'auction_sale_selection_pass' if s=='select' and shown and unchanged else
                ('controller_failure' if s!='select' else 'client_or_protocol_failure'),
                'oracle':{'sale_item_shown':shown,'native_unchanged':unchanged,'sell':sell,
                    'qualified_scope':'sale item selection only; not posting or catalog completeness'}}
        require(t.step('auction.select_sale_item','Select the unbound Recruit\'s Pants for sale.',{
            'select':{'kind':'click','value':point(control),'button':3,'description':'Right-click the visible unbound pants to select them in the auction Sell tab.'},
            'pick':{'kind':'click','value':point(control),'description':'Pick up the pants on the cursor without posting them.'},
            'escape':{'kind':'key','value':'Escape','description':'Close the auction house.'}},outcome,diagnostic_action='select'),'auction_sale_selection_pass')
        state,frame=t.observe('sale_selected');t.receipt['sale_selected']={'state':state,'frame':frame,'controls':controls(t)};t.persist()
    finally:
        errors=[]
        try:t.clean_panels()
        except Exception as e:errors.append('UI cleanup: '+str(e))
        try:fixture.restore()
        except Exception as e:errors.append('NPC fixture: '+str(e))
        after=auction_state();restored=after==baseline
        t.receipt['restoration']={'auction_inventory_money_unchanged':restored,'after':after,'cleanup_errors':errors};t.persist()
        if not restored:raise RuntimeError('sale selection changed the native auction/inventory/money baseline')
        if errors:raise RuntimeError('; '.join(errors))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--point',type=int,nargs=2,required=True);a=p.parse_args()
    if any(not 0<=v<bound for v,bound in zip(a.point,[1280,720])):p.error('requires a bounded observed auctioneer point')
    t=Trial(a.output,controller='code')
    try:suite(t,a.point);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}))
