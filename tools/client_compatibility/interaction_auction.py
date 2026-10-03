"""Open the existing owned-lab auctioneer through ordinary UI inputs."""
import argparse
import json
from pathlib import Path
import time
import uuid
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_operations import controls,click_case,point as control_point
from .interaction_macros import require,edit_case
from .interaction_trade import inventory
from .npc_fixture import NpcFixture
from .observation.journal import entries


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


def query_packets(t,since):
    session=actors.session_entry(t.fixture)['session']
    return [r for r in entries(lab.ROOT/'evidence/world_packets.jsonl') if r.get('session')==session and
        r.get('time',0)>=since and 'AUCTION' in r.get('name','')]


def query_result(t,state,since,kind):
    names={'browse':('CMSG_AUCTION_LIST_ITEMS','SMSG_AUCTION_LIST_RESULT','SMSG_AUCTION_LIST_BUCKETS_RESULT'),
        'owned':('CMSG_AUCTION_LIST_OWNER_ITEMS','SMSG_AUCTION_OWNER_LIST_RESULT','SMSG_AUCTION_LIST_OWNED_ITEMS_RESULT'),
        'bids':('CMSG_AUCTION_LIST_BIDDER_ITEMS','SMSG_AUCTION_BIDDER_LIST_RESULT','SMSG_AUCTION_LIST_BIDDED_ITEMS_RESULT')}
    request,native,modern=names[kind];packets=query_packets(t,since);auction=state.get('auction',{})
    routed=all(any(r['name']==name and r['direction']==direction for r in packets) for name,direction in
        [(request,'to_native'),(native,'from_native'),(modern,'to_client')])
    expected_event={'browse':'AUCTION_HOUSE_BROWSE_RESULTS_UPDATED','owned':'OWNED_AUCTIONS_UPDATED','bids':'BIDS_UPDATED'}[kind]
    event=any(e['event']==expected_event for e in auction.get('events',[]))
    native_empty=not auction_state()['auctions']
    complete=auction.get('full_'+kind) is True and auction.get(kind+'_count')==0
    clean=not state.get('lua_errors') and not state.get('blocked_actions')
    return {'status':'auction_catalog_pass' if routed and event and native_empty and complete and clean else 'client_or_protocol_failure',
        'oracle':{'routed':routed,'event_received':event,'native_empty':native_empty,'visible_complete_empty':complete,
                  'ui_clean':clean,'auction':auction,'packets':packets}}


def restore_search(t,control,before):
    state,_=t.observe('search_cleanup_before')
    if 'AuctionHouseFrame' not in state['panels']:raise RuntimeError('search panel closed before its field restoration')
    t.receipt['cleanup'].append({'source':'code_fixture_search_cleanup','value':before,'point':control_point(control)})
    t.execute({'kind':'edit','point':control_point(control),'value':before})
    restored,frame=t.observe('search_restored');matches=restored.get('auction',{}).get('search_text')==before
    t.receipt['search_restoration']={'matches':matches,'frame':frame};t.persist()
    if not matches:raise RuntimeError('search field differs from its original value')


def suite(t,point,stage_only,query=None):
    actors.session_entry(t.fixture);t.clean_panels();fixture=NpcFixture(t.out,t.fixture,8719,2097152)
    baseline=auction_state();t.receipt['auction_baseline']=baseline;t.persist()
    search_control=None;search_before=None
    try:
        fixture.prepare();t.execute({'kind':'chat','value':'/targetexact '+fixture.npc[2]})
        state,frame=t.observe('auctioneer_staged');t.receipt['staging']={'state':state,'frame':frame};t.persist()
        if state['target'].get('name')!=fixture.npc[2] or not state['target'].get('visible'):
            raise RuntimeError('auctioneer is not visibly targeted')
        if stage_only:return
        open_auction(t,point,fixture.npc[2]);state,frame=t.observe('auction_open')
        t.receipt['auction_open']={'state':state,'frame':frame,'controls':controls(t)};t.persist()
        if not any(p in state['panels'] for p in ['AuctionFrame','AuctionHouseFrame']):raise RuntimeError('auction UI is absent')
        if query and baseline['auctions']:raise RuntimeError('empty-catalog trial requires the native auction baseline to be empty')
        if query=='bids':
            verdict=query_result(t,state,t.receipt['started_at'],'bids');t.receipt['initial_bids']=verdict;t.persist()
            if verdict['status']!='auction_catalog_pass':raise RuntimeError('initial bids catalog did not agree with native data')
        elif query=='owned':
            since=time.time()
            require(click_case(t,'auction.owned','Show the owned auctions tab.',
                lambda c:c['name']=='AuctionHouseFrameAuctionsTab',
                lambda b,a,s:query_result(t,a,since,'owned') if s else {'status':'controller_failure'}),'auction_catalog_pass')
        elif query=='browse':
            search_before=state.get('auction',{}).get('search_text')
            if not isinstance(search_before,str):raise RuntimeError('the ordinary search field is not observed')
            search_control=next((c for c in controls(t) if c['kind']=='EditBox' and c['enabled'] and not c['name']),None)
            if not search_control:raise RuntimeError('the observed auction search EditBox is absent')
            tag='TC442Missing'+uuid.uuid4().hex[:8];t.receipt['search_fixture']={'before':search_before,'tag':tag};t.persist()
            require(edit_case(t,'auction.search_name','Search for the absent owned-test name '+tag+'.',
                lambda c:c['kind']=='EditBox' and not c['name'],tag),'ui_edit_pass')
            since=time.time()
            require(click_case(t,'auction.search','Search the auction house.',lambda c:c['kind']=='Button' and c['text']=='Search',
                lambda b,a,s:query_result(t,a,since,'browse') if s else {'status':'controller_failure'}),'auction_catalog_pass')
        if search_control:
            restore_search(t,search_control,search_before);search_control=None
        require(t.step('auction.close','Close the auction house.',{
            'close':{'kind':'key','value':'Escape','description':'Close the auction house with Escape.'},
            'map':{'kind':'key','value':'m','description':'Open the world map.'},
            'character':{'kind':'key','value':'c','description':'Open equipment.'}},
            lambda b,a,s:{'status':'auction_close_pass' if s=='close' and not any(p in a['panels'] for p in ['AuctionFrame','AuctionHouseFrame']) else
                        ('controller_failure' if s!='close' else 'client_or_protocol_failure')},
            diagnostic_action='close'),'auction_close_pass')
    finally:
        cleanup_errors=[]
        try:
            if search_control:
                restore_search(t,search_control,search_before)
            t.clean_panels()
        except Exception as error:cleanup_errors.append(f'UI cleanup: {type(error).__name__}: {error}')
        try:fixture.restore()
        except Exception as error:cleanup_errors.append(f'NPC fixture: {type(error).__name__}: {error}')
        # A disconnected client must not prevent the independent native check.
        after=auction_state();restoration={'auction_inventory_money_unchanged':after==baseline,
            'after':after,'cleanup_errors':cleanup_errors};t.receipt['restoration']=restoration;t.persist()
        try:
            state,frame=t.observe('auction_restored');restoration['frame']=frame
        except Exception as error:cleanup_errors.append(f'Final observation: {type(error).__name__}: {error}')
        t.persist()
        if after!=baseline:raise RuntimeError('auction opening changed native auctions/inventory/money')
        if cleanup_errors:raise RuntimeError('; '.join(cleanup_errors))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--point',type=int,nargs=2);p.add_argument('--stage-only',action='store_true')
    p.add_argument('--query',choices=['browse','owned','bids']);a=p.parse_args()
    if a.stage_only and a.query:p.error('staging does not run a catalog query')
    if not a.stage_only and (not a.point or any(not 0<=v<bound for v,bound in zip(a.point,[1280,720]))):p.error('requires a bounded observed auctioneer point')
    t=Trial(a.output,controller='code')
    try:suite(t,a.point,a.stage_only,a.query);t.receipt['completed']=True
    except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}))
