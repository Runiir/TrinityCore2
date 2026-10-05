"""Read a disposable native two-page letter through stock bag and page controls."""
import argparse,hashlib,json,struct,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_operations import command,click_case,point
from .interaction_macros import require
from .interaction_inventory_moves import slot_control
from .interaction_crafting import fixture_command
from .interaction_fixture_permissions import item_fixture_permission
from .interaction_observation import read_page
from .interaction_bridge_restoration import capture,restore
from .interaction_trade import inventory
from .interaction_quest_link import detail as quest_detail,saved as saved_quests
from .interaction_lifecycle import Packets
from .observation.inventory import Inventory
from .world.buffer import Reader

BOOK=910
TITLE='An Undelivered Letter'
CATALOG_SHA='bd21d2a012c4a983dc3179de84d63abd1cfcd1f7063d0785426d75636dd24c06'
PAGE_IDS=(18,19)


def canonical(value):return json.loads(json.dumps(value))


def contract():
    path=lab.ROOT/'data/dbc/enUS/Item-sparse.db2'
    if lab.sha256(path)!=CATALOG_SHA:raise RuntimeError('pinned native readable-item catalog changed')
    body=path.read_bytes();h=struct.unpack_from('<4s11I',body)
    if h[0]!=b'WDB2' or (h[2],h[3],h[6])!=(133,532,15595):
        raise RuntimeError('native readable-item catalog layout/build differs')
    start=48+(h[9]-h[8]+1)*6
    if len(body)!=start+h[1]*h[3]+h[4]:raise RuntimeError('native readable-item catalog boundary differs')
    row=next((struct.unpack_from('<133I',body,start+i*h[3]) for i in range(h[1])
        if struct.unpack_from('<I',body,start+i*h[3])[0]==BOOK),None)
    strings=body[start+h[1]*h[3]:]
    # SpellCategoryCooldown has five columns. Stale struct comments omit three;
    # the raw DB2 PageText column is104, and Display is99.
    if (row is None or strings[row[99]:].split(b'\0',1)[0].decode()!=TITLE or
        row[104:108]!=(18,0,0,0) or row[13:21]!=(0,)*8 or row[68:73]!=(0,)*5):
        raise RuntimeError('readable letter identity, pages or use prerequisites differ')
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT ID,Text,NextPageID FROM client442_world.page_text WHERE ID IN (18,19) ORDER BY ID')
        pages=q.fetchall()
    if (len(pages)!=2 or [r[0] for r in pages]!=list(PAGE_IDS) or [r[2] for r in pages]!=[19,0] or
        any(len(r[1].encode())>2048 for r in pages)):
        raise RuntimeError('native letter page chain differs from the bounded fixture')
    return {'item':BOOK,'title':TITLE,'catalog_sha256':CATALOG_SHA,
        'pages':[{'id':r[0],'text':r[1],'next':r[2],
                  'sha256':hashlib.sha256(r[1].encode()).hexdigest()} for r in pages]}


def detail(t,label):
    try:
        state,frame=read_page(t,label,'itemtext','/tcui itemtext')
        probe=state['item_text_probe']
        t.receipt.setdefault('item_text_details',{})[label]={'state':state,'frame':frame};t.persist()
        return probe
    finally:
        command(t,'/tcui');t.observe(label+'_passive_cycle')


def book_fixture(t,oracle,delta):
    expected=oracle.poll().count(BOOK)+delta
    if expected not in (0,1):raise RuntimeError('readable fixture exceeds one disposable letter')
    with item_fixture_permission(t):
        fixture_command(t,'/cleartarget','readable fixture commands target only the owned actor')
        fixture_command(t,f'.additem {BOOK} {delta}','prepare one letter' if delta==1 else 'remove only the disposable letter')
        deadline=time.monotonic()+12
        while oracle.poll().count(BOOK)!=expected:
            if time.monotonic()>deadline:raise RuntimeError('native readable fixture did not settle; no input replay')
            time.sleep(.2)
        lab.server_command('saveall');time.sleep(1)
        fixture_rows=[r for r in canonical(inventory())['items'] if r[0]==t.fixture['guid'] and r[4]==BOOK]
        if (expected==1 and (len(fixture_rows)!=1 or fixture_rows[0][1]!=0 or
                not 23<=fixture_rows[0][2]<39 or fixture_rows[0][5:]!=[1,t.fixture['guid']])):
            raise RuntimeError('native readable fixture is not one attributable backpack item')
        if expected==0 and fixture_rows:raise RuntimeError('removed readable fixture is still in native inventory')
        if expected==1:t.receipt['prepared_readable_native_row']=fixture_rows[0]
        t.receipt.setdefault('readable_fixture_counts',[]).append({'delta':delta,'native_count':expected});t.persist()


def page_checks(probe,expected,number):
    return {'stock_window':probe.get('visible') is True,'contents_visible':probe.get('contents_visible') is True,
        'title':probe.get('title')==TITLE and probe.get('item')==TITLE,'page':probe.get('page')==number,
        'exact_native_text':probe.get('text')==expected['text'],
        'untruncated_text':probe.get('text_truncated') is False and
            probe.get('text_length')==len(expected['text'].encode()),
        'next':probe.get('has_next')==(number==1) and probe.get('next_visible')==(number==1),
        'previous':probe.get('previous_visible')==(number==2)}


def wire_checks(rows,native,row,spec):
    def bodies(name,direction):
        return [bytes.fromhex(p['body']) for p in rows if p['name']==name and p['direction']==direction]
    reads=bodies('CMSG_READ_ITEM','to_native')
    native_ok=bodies('SMSG_READ_ITEM_OK','from_native')
    modern_ok=bodies('SMSG_READ_ITEM_RESULT_OK','to_client')
    checks={'native_read_position':reads==[bytes([255,row['slot']+22])],
        'native_read_owned_guid':native_ok==[struct.pack('<Q',native['guid'])]}
    identities=[]
    for body in modern_ok:
        r=Reader(body);identities.append(r.guid());r.end()
    identity=(native['guid']&0xffffffff,(3<<58)|(1<<42))
    checks['modern_read_owned_guid']=identities==[identity]
    native_pages=[]
    for body in bodies('SMSG_PAGE_TEXT_QUERY_RESPONSE','from_native'):
        r=Reader(body);id,=r.unpack('I');text=bytearray()
        while (value:=r.raw(1))!=b'\0':text.extend(value)
        next,=r.unpack('I');r.end();native_pages.append((id,text.decode(),next))
    expected=[(p['id'],p['text'],p['next']) for p in spec['pages']]
    checks['exact_native_chain']=native_pages==expected
    modern_chains=[]
    for body in bodies('SMSG_QUERY_PAGE_TEXT_RESPONSE','to_client'):
        r=Reader(body);root,=r.unpack('I');allow=r.bits(1);pages=[]
        if allow:
            count,=r.unpack('I')
            if count>64:raise RuntimeError('modern page chain exceeds bound')
            for _ in range(count):
                id,next,condition,flags=r.unpack('IIiB');length=r.bits(12)
                pages.append((id,r.raw(length).decode(),next,condition,flags))
        r.end();modern_chains.append((root,allow,pages))
    checks['exact_modern_chain']=modern_chains==[(18,1,[(*p,0,0) for p in expected])]
    queries=[]
    for body in bodies('CMSG_PAGE_TEXT_QUERY','to_native'):
        queries.append(struct.unpack('<IQ',body))
    checks['native_page_query']=queries in ([(18,0)],[(18,native['guid'])])
    return checks


def suite(t):
    if t.fixture['guid']!=1:raise RuntimeError('requires the owned primary warrior')
    session=actors.session_entry(t.fixture)['session'];oracle=Inventory(lab.ROOT,session,1).poll()
    t.clean_panels();state,quest=quest_detail(t,'readable_original_quest')
    if state.get('observer_version')!=122 or state.get('target',{}).get('exists') or oracle.count(BOOK):
        raise RuntimeError('requires observer122, no target and no pre-existing fixture letter')
    native=canonical(capture(t));lab.server_command('saveall');time.sleep(1)
    original=canonical(inventory());quests=saved_quests(1);spec=contract()
    t.receipt.update(native_baseline=native,original_inventory=original,original_quest_log=quest,
        original_native_quests=quests,item_text_contract=spec,custom_script_permission='blocked_by_user',
        qualified_scope='Owned native letter910 only: ordinary bag right-click, exact two-page text, stock next/previous and Close button. Dynamic item text, other materials and denied/error variants remain open.');t.persist()
    packets=Packets(session);prepared=None
    try:
        if detail(t,'readable_original').get('visible'):raise RuntimeError('original item-text panel was already open')
        book_fixture(t,oracle,1)
        require(t.step('ui_misc.item_text_bags','Open the bags containing the disposable readable letter.',
            {'open':{'kind':'key','value':'b','description':'Open the bags with B.'}},
            lambda b,a,s:{'status':'readable_bag_pass' if len([r for r in a.get('bag_items',[])
                if r['id']==BOOK and r['count']==1 and not r['locked']])==1 else 'client_or_protocol_failure'},
            diagnostic_action='open',await_state=lambda s:any(r['id']==BOOK for r in s.get('bag_items',[]))),
            'readable_bag_pass')
        state,frame=t.observe('readable_fixture');rows=[r for r in state['bag_items'] if r['id']==BOOK and r['count']==1]
        if len(rows)!=1:raise RuntimeError('one observed readable letter is required')
        row=rows[0];prepared=oracle.slot(row['bag'],row['slot']);control=slot_control(t,row['bag'],row['slot'])
        if not control or prepared['id']!=BOOK or prepared['count']!=1:raise RuntimeError('public/native letter position differs')
        t.receipt['readable_fixture']={'native':prepared,'public':row,'frame':frame,'control':control};t.persist()
        started=time.time()
        def opened(b,a,s):
            probe=detail(t,'readable_open');checks=page_checks(probe,spec['pages'][0],1)
            trace=[p for p in packets.since(started) if p['name'] in ('CMSG_READ_ITEM','SMSG_READ_ITEM_OK',
                'SMSG_READ_ITEM_RESULT_OK','CMSG_QUERY_PAGE_TEXT','CMSG_PAGE_TEXT_QUERY',
                'SMSG_PAGE_TEXT_QUERY_RESPONSE','SMSG_QUERY_PAGE_TEXT_RESPONSE')]
            checks.update(wire_checks(trace,prepared,row,spec))
            checks.update(ordinary_right_click=s=='read',owned_item_preserved=oracle.poll().slot(row['bag'],row['slot'])==prepared,
                ui_clean=not a.get('lua_errors') and not a.get('blocked_actions'))
            return {'status':'stock_item_text_pass' if all(checks.values()) else 'client_or_protocol_failure',
                'oracle':{'checks':checks,'public':probe,'packets':trace}}
        require(t.step('ui_misc.item_text_open','Read the observed letter through the stock bag right-click.',
            {'read':{'kind':'click','value':point(control),'button':3,'description':'Right-click the observed An Undelivered Letter.'}},
            opened,diagnostic_action='read',await_state=lambda s:'ItemTextFrame' in s['panels']),'stock_item_text_pass')
        for number,button,label in [(2,'ItemTextNextPageButton','next'),(1,'ItemTextPrevPageButton','previous')]:
            def changed(b,a,s):
                probe=detail(t,'readable_'+label);checks=page_checks(probe,spec['pages'][number-1],number)
                checks.update(ordinary_button=bool(s),owned_item_preserved=oracle.poll().slot(row['bag'],row['slot'])==prepared,
                    ui_clean=not a.get('lua_errors') and not a.get('blocked_actions'))
                return {'status':'stock_item_text_page_pass' if all(checks.values()) else 'client_or_protocol_failure',
                    'oracle':{'checks':checks,'public':probe}}
            require(click_case(t,'ui_misc.item_text_page.'+label,'Turn the letter with its stock '+label+' page button.',
                lambda c:c['name']==button,changed),'stock_item_text_page_pass')
        before_close=detail(t,'readable_before_close')
        def closed(b,a,s):
            probe=detail(t,'readable_closed');checks={'ordinary_close':bool(s),'panel_closed':probe.get('visible') is False,
                'closed_event':probe['event_counts']['ITEM_TEXT_CLOSED']>before_close['event_counts']['ITEM_TEXT_CLOSED'],
                'owned_item_preserved':oracle.poll().slot(row['bag'],row['slot'])==prepared,
                'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
            return {'status':'stock_item_text_close_pass' if all(checks.values()) else 'client_or_protocol_failure',
                'oracle':{'checks':checks,'public':probe}}
        require(click_case(t,'ui_misc.item_text_close','Close the letter with its stock Close button.',
            lambda c:c['name']=='ItemTextCloseButton',closed),'stock_item_text_close_pass')
    finally:
        t.clean_panels()
        if oracle.poll().count(BOOK):
            fixed=t.receipt.get('prepared_readable_native_row')
            current=[r for r in canonical(inventory())['items'] if r[0]==1 and r[4]==BOOK]
            if not fixed or current!=[fixed]:
                raise RuntimeError('disposable readable letter identity differs; refusing removal')
            book_fixture(t,oracle,-1)
        lab.server_command('saveall');time.sleep(1)
        restore(t,native);state,current=quest_detail(t,'readable_final_quest')
        checks={'inventory_money':canonical(inventory())==original,'letter_absent':oracle.poll().count(BOOK)==0,
            'quest_layout':current==quest,'native_quests':saved_quests(1)==quests,
            'same_session':actors.session_entry(t.fixture)['session']==session,
            'panels_closed':not state.get('panels') and not state.get('bags'),'chat_closed':not state.get('chat_edit_open'),
            'no_lua_errors':not state.get('lua_errors'),'no_blocked_actions':not state.get('blocked_actions')}
        t.receipt['readable_restoration']={'checks':checks};t.persist()
        if not all(checks.values()):raise RuntimeError('readable letter restoration differs from the original fixture')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    t=Trial(a.output,controller='code',chat_key_hold=1.2)
    try:suite(t);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:
        t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt[k] for k in ('completed','failure')}),flush=True)
