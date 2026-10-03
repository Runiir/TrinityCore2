"""Open the existing owned-lab auctioneer through ordinary UI inputs."""
import argparse
import json
from pathlib import Path
import time
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_operations import controls,click_case
from .interaction_macros import require
from .interaction_trade import inventory
from .npc_fixture import NpcFixture


def auction_state():
    lab.server_command('saveall');time.sleep(1)
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT id,houseid,itemguid,itemowner,buyoutprice,time,buyguid,lastbid,startbid,deposit '
                  'FROM client442_characters.auctionhouse ORDER BY id')
        rows=q.fetchall()
    return {'auctions':rows,'inventory':inventory()}


def open_auction(t,point,name):
    panels=['AuctionFrame','AuctionHouseFrame']
    require(t.step('auction.interact','Speak to the nearby auctioneer '+name+'.',{
        'interact':{'kind':'click','value':point,'button':3,'description':'Right-click the visible nearby auctioneer '+name+'.'},
        'map':{'kind':'key','value':'m','description':'Open the world map.'},
        'character':{'kind':'key','value':'c','description':'Open character equipment.'}},
        lambda b,a,s:{'status':'npc_interaction_pass' if s=='interact' and any(p in a['panels'] for p in panels+['GossipFrame']) else
                    ('controller_failure' if s!='interact' else 'client_or_protocol_failure'),
                    'oracle':{'panels':a['panels'],'errors':a.get('errors'),'lua_errors':a.get('lua_errors')}},
        diagnostic_action='interact'),'npc_interaction_pass')
    state,_=t.observe('auctioneer_response')
    if 'GossipFrame' in state['panels']:
        require(click_case(t,'auction.gossip','Open the auction house.',lambda c:'auction' in c['text'].lower(),
            lambda b,a,s:{'status':'auction_open_pass' if s and any(p in a['panels'] for p in panels) else
                        ('controller_failure' if not s else 'client_or_protocol_failure')}),'auction_open_pass')


def suite(t,point,stage_only):
    actors.session_entry(t.fixture);t.clean_panels();fixture=NpcFixture(t.out,t.fixture,8719,2097152)
    baseline=auction_state();t.receipt['auction_baseline']=baseline;t.persist()
    try:
        fixture.prepare();t.execute({'kind':'chat','value':'/targetexact '+fixture.npc[2]})
        state,frame=t.observe('auctioneer_staged');t.receipt['staging']={'state':state,'frame':frame};t.persist()
        if state['target'].get('name')!=fixture.npc[2] or not state['target'].get('visible'):
            raise RuntimeError('auctioneer is not visibly targeted')
        if stage_only:return
        open_auction(t,point,fixture.npc[2]);state,frame=t.observe('auction_open')
        t.receipt['auction_open']={'state':state,'frame':frame,'controls':controls(t)};t.persist()
        if not any(p in state['panels'] for p in ['AuctionFrame','AuctionHouseFrame']):raise RuntimeError('auction UI is absent')
        require(t.step('auction.close','Close the auction house.',{
            'close':{'kind':'key','value':'Escape','description':'Close the auction house with Escape.'},
            'map':{'kind':'key','value':'m','description':'Open the world map.'},
            'character':{'kind':'key','value':'c','description':'Open equipment.'}},
            lambda b,a,s:{'status':'auction_close_pass' if s=='close' and not any(p in a['panels'] for p in ['AuctionFrame','AuctionHouseFrame']) else
                        ('controller_failure' if s!='close' else 'client_or_protocol_failure')},
            diagnostic_action='close'),'auction_close_pass')
    finally:
        try:t.clean_panels()
        finally:fixture.restore()
        after=auction_state();state,frame=t.observe('auction_restored')
        t.receipt['restoration']={'auction_inventory_money_unchanged':after==baseline,'after':after,'frame':frame};t.persist()
        if after!=baseline:raise RuntimeError('auction opening changed native auctions/inventory/money')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--point',type=int,nargs=2);p.add_argument('--stage-only',action='store_true');a=p.parse_args()
    if not a.stage_only and (not a.point or any(not 0<=v<bound for v,bound in zip(a.point,[1280,720]))):p.error('requires a bounded observed auctioneer point')
    t=Trial(a.output,controller='code')
    try:suite(t,a.point,a.stage_only);t.receipt['completed']=True
    except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}))
