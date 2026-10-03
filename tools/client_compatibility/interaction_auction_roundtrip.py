"""Post/cancel one owned item, collect its return and restore exact resources."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_macros import require,edit_case
from .interaction_operations import controls,click_case,point
from .interaction_auction import auction_state,query_packets
from .interaction_auction import open_auction
from .npc_fixture import NpcFixture
from .interaction_auction_sell import suite as sell_suite
from .interaction_mail import mailbox_state
from .interaction_mail_actions import open_mailbox,letter
from .mailbox_fixture import MailboxFixture
from .interaction_inventory_moves import move
from .observation.inventory import Inventory
from .interaction_fixture_permissions import money_fixture_permission
from .interaction_crafting import fixture_command


def set_price(t):
    fields=[c for c in t.receipt['sale_selected']['controls'] if c['kind']=='EditBox' and not c['name']]
    if len(fields)!=3:raise RuntimeError('requires the observed three buyout money fields')
    gold=min(fields,key=lambda c:c['x'])
    require(edit_case(t,'auction.set_buyout','Set the buyout price to one gold.',
        lambda c:c['x']==gold['x'] and c['y']==gold['y'],'1'),'ui_edit_pass')
    state,frame=t.observe('price_ready');sell=state.get('auction',{}).get('sell',{})
    t.receipt['price_ready']={'sell':sell,'frame':frame};t.persist()
    if sell.get('buyout')!=10000 or not sell.get('post_enabled'):raise RuntimeError('stock sale price is not ready')


def post(t,baseline):
    set_price(t);since=time.time()
    def outcome(b,a,selected):
        native=auction_state();rows=native['auctions'];packets=query_packets(t,since)
        row=rows[0] if len(rows)==1 else None
        expected=(row and row[1:5]==(2,4,1,10000) and row[6:9]==(0,0,10000))
        command=any(p['name']=='SMSG_AUCTION_COMMAND_RESULT' and p['direction']=='from_native'
            and int.from_bytes(bytes.fromhex(p['body'])[8:12],'little')==0 for p in packets)
        gone=not any(r['bag']==0 and r['slot']==8 for r in a.get('bag_items',[]))
        return {'status':'auction_post_pass' if selected and expected and command and gone and not a.get('lua_errors') else
            ('controller_failure' if not selected else 'client_or_protocol_failure'),
            'oracle':{'native_after':native,'packets':packets,'expected_native_listing':bool(expected),
                'native_success':command,'sale_item_removed':gone,'qualified_scope':'plain buyout-only posting; fees remain separate'}}
    require(click_case(t,'auction.post','Create the one-gold pants auction.',lambda c:c['text']=='Create Auction',outcome),'auction_post_pass')
    rows=auction_state()['auctions']
    if len(rows)!=1 or rows[0][2:4]!=(4,1):raise RuntimeError('posted fixture auction changed')
    row=rows[0];t.receipt['posted_auction']=row;t.persist();return row


def cancel(t,row):
    require(click_case(t,'auction.show_owned','Show the owned auction listing.',lambda c:c['name']=='AuctionHouseFrameAuctionsTab',
        lambda b,a,s:{'status':'auction_owned_populated_pass' if s and a.get('auction',{}).get('full_owned')
            and a.get('auction',{}).get('owned_count')==1 and any(r.get('auction_id')==row[0] and r.get('id')==39
                and r.get('buyout')==10000 for r in a.get('auction',{}).get('owned',[])) and not a.get('lua_errors')
            else ('controller_failure' if not s else 'client_or_protocol_failure')}),'auction_owned_populated_pass')
    state,frame=t.observe('owned_listing');t.receipt['owned_listing']={'state':state,'frame':frame,'controls':controls(t)};t.persist()
    def selected(b,a,s):
        return {'status':'auction_select_owned_pass' if s and a.get('auction',{}).get('selected_id')==row[0]
            and a.get('auction',{}).get('cancel_enabled') else ('controller_failure' if not s else 'client_or_protocol_failure')}
    # The reviewed price-column Frame absorbs center clicks. Select the item
    # end inside the passively measured owned row; prior failed clicks remain.
    control=next(c for c in t.receipt['owned_listing']['controls'] if c.get('auction_id')==row[0] and c['enabled'])
    width=control.get('width',0)*1280/65535
    if width<80:raise RuntimeError('owned row has no measured item-end click bounds')
    item_point=point(control);item_point[0]=round(item_point[0]-width/2+20)
    selection=t.step('auction.select_owned_item_end','Select the posted auction at its item end.',
        {'item_end':{'kind':'click','value':item_point,'description':'Click the observed auction row near its item icon.'}},
        lambda b,a,s:selected(b,a,s=='item_end'),diagnostic_action='item_end')
    require(selection,'auction_select_owned_pass')
    require(click_case(t,'auction.cancel_dialog','Cancel the selected auction.',lambda c:c['text']=='Cancel Auction',
        lambda b,a,s:{'status':'auction_cancel_dialog_pass' if s and 'StaticPopup1' in a['panels'] else
            ('controller_failure' if not s else 'client_or_protocol_failure')}),'auction_cancel_dialog_pass')
    since=time.time()
    def canceled(b,a,s):
        gone=not auction_state()['auctions'];packets=query_packets(t,since)
        routed=any(p['name']=='CMSG_AUCTION_REMOVE_ITEM' and p['direction']=='to_native' for p in packets)
        return {'status':'auction_cancel_pass' if s and gone and routed and not a.get('lua_errors') else
            ('controller_failure' if not s else 'client_or_protocol_failure'),
            'oracle':{'native_auction_absent':gone,'native_routed':routed,'packets':packets}}
    require(click_case(t,'auction.confirm_cancel','Confirm cancellation of the selected auction.',
        lambda c:c['name']=='StaticPopup1Button1' and c['text'] in ['Accept','Yes','Okay'],canceled),'auction_cancel_pass')


def recover_mail(t,point,baseline,deposit):
    state=mailbox_state();new=[r for r in state['mails'] if r[0] not in {m[0] for m in baseline['mails']}]
    if len(new)!=1 or new[0][1:4]!=(2,2,1) or new[0][5:7]!=(0,0) or not new[0][8]:
        raise RuntimeError('requires one native alliance-auction cancellation return')
    mail=new[0];attached=[r for r in state['attachments'] if r[0]==mail[0]]
    if attached!=[(mail[0],4,39,1)]:raise RuntimeError('auction return does not contain the exact original pants')
    t.receipt['cancellation_mail']={'native':mail,'attachments':attached};t.persist()
    folder=t.out/'mailbox';folder.mkdir(mode=0o700)
    fixture=MailboxFixture(folder,t.fixture)
    try:
        fixture.prepare();staged,frame=t.observe('mailbox_staged');t.receipt['mailbox_staging']={'state':staged,'frame':frame};t.persist()
        open_mailbox(t,point);shown,_=t.observe('return_inbox')
        # The public header localizes the encoded auction subject. Native state
        # above pins the sole return's original item GUID and auction sender.
        candidates=[r for r in shown.get('mail',{}).get('inbox',[]) if r['sender']=='Alliance Auction House'
            and r['items']==1 and not r['money'] and not r['cod']]
        if len(candidates)!=1:raise RuntimeError('the unique native auction return is outside the observed inbox')
        letter_row=candidates[0];display_subject=letter_row['subject']
        t.receipt['return_subject']={'native_encoded':mail[4],'public_localized':display_subject};t.persist()
        require(click_case(t,'auction.read_return','Read the auction cancellation return.',
            lambda c:c['name']=='MailItem'+str(letter_row['index'])+'Button',
            lambda b,a,s:{'status':'auction_return_read_pass' if s and a.get('mail',{}).get('open',{}).get('subject')==display_subject
                else ('controller_failure' if not s else 'client_or_protocol_failure')}),'auction_return_read_pass')
        require(click_case(t,'auction.collect_return','Take the returned Recruit\'s Pants.',lambda c:c['name']=='OpenMailAttachmentButton1',
            lambda b,a,s:{'status':'auction_return_collect_pass' if s and any(r['id']==39 and r['count']==1 for r in a.get('bag_items',[]))
                and not a.get('mail',{}).get('open',{}).get('attachments') and not letter(mail[4])[9] else
                ('controller_failure' if not s else 'client_or_protocol_failure')}),'auction_return_collect_pass')
        require(click_case(t,'auction.delete_return','Delete the now-empty auction cancellation letter.',
            lambda c:c['name']=='OpenMailDeleteButton' and c['text']=='Delete',
            lambda b,a,s:{'status':'auction_return_delete_pass' if s and letter(mail[4]) is None else
                ('controller_failure' if not s else 'client_or_protocol_failure')}),'auction_return_delete_pass')
        t.clean_panels();t.execute({'kind':'key','value':'b'})
        native=Inventory(lab.ROOT,actors.session_entry(t.fixture)['session'],1).poll()
        positions=[(bag,slot) for bag in range(5) for slot in range(1,17) if native.slot(bag,slot)['guid']==((0x4000<<48)|4)]
        if len(positions)!=1:raise RuntimeError('returned original item is not uniquely in owned bags')
        source=positions[0]
        if source!=(0,8):
            if native.slot(0,8)['guid']:raise RuntimeError('original bag slot became occupied')
            require(move(t,native,source,(0,8),native.slot(*source),'auction.restore_slot'),'inventory_move_pass')
        t.clean_panels();native.poll()
        before=next(r[1] for r in baseline['inventory']['money'] if r[0]==1);delta=before-native.money()
        if delta not in [0,deposit]:raise RuntimeError('auction money delta differs from its native deposit')
        t.receipt['deposit']={'native_deposit':deposit,'native_charge':delta,'stock_quote':'zero in the reviewed cheap-item UI; fee discrepancy remains open'};t.persist()
        if delta:
            fixture_command(t,'/cleartarget','restore auction deposit only on the owned actor')
            with money_fixture_permission(t):fixture_command(t,f'.modify money {delta}','restore only the recorded auction deposit charge')
    finally:
        t.clean_panels();fixture.restore()


def suite(t,auction_point,mail_point):
    baseline=mailbox_state();t.receipt['mailbox_baseline']=baseline;t.persist()
    def transaction(t,auction_baseline,fixture):
        try:
            row=post(t,auction_baseline)
            cancel(t,row);t.clean_panels();fixture.restore();fixture.rows=[]
            recover_mail(t,mail_point,baseline,row[9])
        except Exception as error:
            t.receipt['transaction_failure']=f'{type(error).__name__}: {error}';t.persist();raise
    try:sell_suite(t,auction_point,catalog=True,transaction=transaction)
    finally:
        after=mailbox_state();t.receipt['roundtrip_restoration']={'mail_inventory_money_restored':after==baseline,'after':after};t.persist()
        if after!=baseline:raise RuntimeError('auction roundtrip requires cleanup; preserve native return/listing for recovery')


def recover(t,source,auction_point,mail_point):
    previous=json.loads((source/'episode.json').read_text())
    if not previous.get('finished_at') or previous['actor']!=t.receipt['actor']:
        raise RuntimeError('recovery requires a closed receipt for the same owned actor')
    old=previous['runtime']['worldserver'];current=lab.owned_process('worldserver')
    if (old['pid'],old['start_ticks'])!=(current['pid'],current['start_ticks']):
        raise RuntimeError('recovery requires the same owned native server')
    row=tuple(previous['posted_auction']);baseline=previous['mailbox_baseline']
    listing=auction_state()['auctions']
    if listing and listing!=((row),):raise RuntimeError('recovery listing differs from the exact posted auction')
    t.receipt['recovery_source']=str(source);t.receipt['posted_auction']=row;t.receipt['mailbox_baseline']=baseline;t.persist()
    fixture=NpcFixture(t.out,t.fixture,8719,2097152)
    try:
        if listing:
            t.clean_panels();fixture.prepare();t.execute({'kind':'chat','value':'/targetexact '+fixture.npc[2]})
            open_auction(t,auction_point,fixture.npc[2]);cancel(t,row)
            t.clean_panels();fixture.restore();fixture.rows=[]
        else:
            t.receipt['recovery_stage']='already canceled; recover only the uniquely pinned native return';t.persist()
        recover_mail(t,mail_point,baseline,row[9])
    except Exception as error:
        t.receipt['transaction_failure']=f'{type(error).__name__}: {error}';t.persist();raise
    finally:
        t.clean_panels();fixture.restore();after=mailbox_state()
        # Persisted baseline arrays are normalized before comparing SQL tuples.
        restored=json.loads(json.dumps(after))==baseline
        t.receipt['roundtrip_restoration']={'mail_inventory_money_restored':restored,'after':after};t.persist()
        if not restored or auction_state()['auctions']:raise RuntimeError('posted auction recovery still requires cleanup')


def stage(t):
    fixture=MailboxFixture(t.out,t.fixture)
    try:
        t.clean_panels();fixture.prepare();state,frame=t.observe('mailbox_point_review')
        t.receipt['staging']={'state':state,'frame':frame};t.persist()
    finally:fixture.restore()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--recover-from',type=Path)
    p.add_argument('--stage-mail',action='store_true');p.add_argument('--auction-point',type=int,nargs=2);p.add_argument('--mail-point',type=int,nargs=2)
    a=p.parse_args()
    if not a.stage_mail and (not a.auction_point or not a.mail_point):p.error('requires separately reviewed auction and mailbox points')
    if any(not 0<=v<bound for point in [a.auction_point,a.mail_point] if point for v,bound in zip(point,[1280,720])):
        p.error('fixture points must be within the owned 1280x720 client')
    t=Trial(a.output,controller='code')
    try:
        if a.stage_mail:stage(t)
        elif a.recover_from:recover(t,a.recover_from,a.auction_point,a.mail_point)
        else:suite(t,a.auction_point,a.mail_point)
        t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
