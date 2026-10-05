"""Add one owned offline friend, check stock errors, and restore the social rows."""
import argparse,json,struct,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_social import actor
from .interaction_control_target import click,edit,target
from .interaction_operations import controls,point
from .interaction_chat_player_actions import menu_click
from .interaction_macros import require
from .interaction_bridge_restoration import capture,restore
from .interaction_quest_link import detail as quest_detail,saved as saved_quests
from .interaction_trade import inventory
from .interaction_lifecycle import Packets
from .world.buffer import Reader

FRIEND='Harnessdwarf'
REMOVE_NAME=FRIEND+'-Client442Lab'
MISSING='Zzqvxfixture'
GUID=3
HIGH=(2<<58)|(1<<42)


def canonical(value):return json.loads(json.dumps(value))


def social():
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT guid,friend,flags,note FROM client442_characters.character_social '
                  'WHERE guid IN (1,2,3) ORDER BY guid,friend')
        return canonical(q.fetchall())


def public(rows):
    return sorted(rows or [],key=lambda r:r['name'])


def offline_fixture():
    with actor('scout'):owner=actors.load()['account_id']
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT * FROM client442_characters.characters WHERE guid=3 AND account=%s AND name=%s',
                  (owner,FRIEND));row=q.fetchone()
        if row is None:raise RuntimeError('the offline dwarf is not owned by the scout account')
        record=dict(zip([r[0] for r in q.description],row))
        q.execute('SELECT guid FROM client442_characters.characters WHERE name=%s',(MISSING,))
        if q.fetchone():raise RuntimeError('the nonexistent-name fixture now exists')
    if record['online'] or record['race']!=3 or record['level']!=1:
        raise RuntimeError('requires the unchanged offline level1 owned dwarf')
    return record


def wire_checks(rows,name,guid,result,remove=False):
    def bodies(op,direction):
        return [bytes.fromhex(r['body']) for r in rows if r['name']==op and r['direction']==direction]
    request='CMSG_DEL_FRIEND' if remove else 'CMSG_ADD_FRIEND'
    native_request=struct.pack('<Q',guid) if remove else name.encode()+b'\0\0'
    requests=[]
    for body in bodies(request,'from_client'):
        r=Reader(body)
        if remove:requests.append((r.unpack('I')[0],r.guid()))
        else:
            length,note=r.bits(9),r.bits(9)
            requests.append((r.raw(length).decode(),r.raw(note).decode()))
        r.end()
    expected=(1,(guid,HIGH)) if remove else (name,'')
    native=struct.pack('<BQ',result,guid)+(b'\0' if result==7 else b'')
    replies=[]
    for body in bodies('SMSG_FRIEND_STATUS','to_client'):
        r=Reader(body);status=r.unpack('B')[0];player=r.guid();account=r.guid()
        realm,connected,area,level,klass=r.unpack('IBIII');length=r.bits(10);note=r.raw(length).decode();r.end()
        replies.append((status,player,account,realm,connected,area,level,klass,note))
    return {'exact_modern_request':requests==[expected],
        'exact_native_request':bodies(request,'to_native')==[native_request],
        'exact_native_status':bodies('SMSG_FRIEND_STATUS','from_native')==[native],
        'exact_modern_status':replies==[(result,(guid,HIGH if guid else 0),(0,0),1,0,0,0,0,'')]}


def open_friends(t,label):
    require(click(t,label,'Open the stock Friends window.',lambda c:c['name']=='FriendsMicroButton',
        lambda b,a,s:{'status':'friend_window_open' if s and 'FriendsFrame' in a['panels'] else
            'client_or_protocol_failure'},await_state=lambda s:'FriendsFrame' in s['panels']),
        'friend_window_open')


def add_dialog(t,name,label):
    require(click(t,label+'.dialog','Open the stock character Add Friend dialog.',
        lambda c:c['name']=='FriendsFrameAddFriendButton',lambda b,a,s:{'status':'friend_dialog_open' if s and
            'StaticPopup1' in a['panels'] else 'client_or_protocol_failure'}),'friend_dialog_open')
    require(edit(t,label+'.name','Enter the exact owned or verified missing character name.',
        lambda c:c['name']=='StaticPopup1EditBox' and c.get('context')=='Enter name of friend to add:',name),
        'ui_edit_pass')


def operation(t,packets,label,name,guid,result,expected_rows,expected_public,remove=False):
    if not remove:add_dialog(t,name,label)
    else:
        row=target(t,label+'.row',lambda c:c['kind']=='Button' and
            c['name'].startswith('FriendsFrameFriendsScrollFrameButton') and c['text']==FRIEND)
        def menu(b,a,s):
            rows=controls(t);state,frame=t.observe('friends_remove_menu')
            matches=[c for c in rows if c['text']=='Remove Friend' and c['enabled'] and
                c['kind'] in ('Button','MenuItem')]
            checks={'owned_row':row['text']==FRIEND,'ordinary_right_click':s=='menu',
                'stock_menu':any(p in a['panels'] for p in ('ContextMenu','DropDownList1')),
                'one_remove_control':len(matches)==1,'prepared_social_unchanged':social()==
                    sorted(expected_rows+[[1,GUID,1,'']],key=lambda r:(r[0],r[1]))}
            t.receipt['friend_remove_menu']={'checks':checks,'control':row,'controls':rows,'frame':frame,
                'state':state};t.persist()
            return {'status':'friend_remove_menu_pass' if all(checks.values()) else 'client_or_protocol_failure',
                'oracle':{'checks':checks}}
        require(t.step(label+'.menu','Open only the exact owned dwarf friend-row context menu.',
            {'menu':{'kind':'click','value':point(row),'button':3,'hold':.4}},menu,diagnostic_action='menu'),
            'friend_remove_menu_pass')
    started=time.time()
    def outcome(b,a,s):
        trace=[r for r in packets.since(started) if r['name'] in
            ('CMSG_ADD_FRIEND','CMSG_DEL_FRIEND','SMSG_FRIEND_STATUS')]
        checks=wire_checks(trace,name,guid,result,remove)
        checks.update(ordinary_input=bool(s),native_social=social()==expected_rows,
            public_friends=public(a.get('friends'))==public(expected_public),
            friends_ready=a.get('friends_ready') is True,stock_window='FriendsFrame' in a['panels'],
            dialog_closed='StaticPopup1' not in a['panels'],chat_closed=not a.get('chat_edit_open'),
            clean=not a.get('lua_errors') and not a.get('blocked_actions'))
        return {'status':'friend_status_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'packets':trace,'expected_native_result':result,
                'rendered_stock_message_requires_visual_review':True}}
    if remove:
        require(menu_click(t,label,'Remove Friend',outcome,
            await_state=lambda s:not any(r['name']==FRIEND for r in s.get('friends') or [])),
            'friend_status_pass')
    else:
        require(click(t,label,'Confirm the stock Add Friend dialog.',lambda c:c['name']=='StaticPopup1Button1' and
            c['text']=='Accept' and c.get('context')=='Enter name of friend to add:',outcome,
            await_state=lambda s:'StaticPopup1' not in s['panels']),
            'friend_status_pass')
    state,frame=t.observe(label.replace('.','_')+'_rendered')
    t.receipt.setdefault('friend_rendered_outcomes',[]).append({'case':label,'name':name,'native_result':result,
        'state':state,'frame':frame});t.persist()


def close_friends(t):
    state,frame=t.observe('friends_close_guard')
    if state.get('chat_edit_open'):
        if (not state.get('chat_edit_focused') or state.get('chat_edit_text')!=
                '/removefriend '+REMOVE_NAME):
            raise RuntimeError('friend cleanup refuses an unrelated pending chat edit')
        t.receipt['friend_pending_cancel']={'frame':frame,'text':state['chat_edit_text'],
            'input':{'kind':'key','value':'Escape','hold':.4},'submitted':False};t.persist()
        t.execute(t.receipt['friend_pending_cancel']['input'])
        state,frame=t.observe('friends_pending_cancelled')
        if state.get('chat_edit_open'):raise RuntimeError('exact pending friend edit did not cancel')
    if 'FriendsFrame' in state['panels']:
        require(click(t,'fixture.friends.close','Close Friends through its observed stock Close button.',
            lambda c:c['name']=='FriendsFrameCloseButton',lambda b,a,s:{'status':'friend_window_closed' if s and
                'FriendsFrame' not in a['panels'] else 'client_or_protocol_failure'},
            await_state=lambda s:'FriendsFrame' not in s['panels']),'friend_window_closed')
    t.clean_panels()


def restored(t,old):
    restore(t,old['native_baseline'])
    state,current_quest=quest_detail(t,'friends_restored')
    checks={'native_social':social()==old['original_social'],
        'public_friends':public(state.get('friends'))==old['original_public_friends'],
        'inventory_money':canonical(inventory())==old['original_inventory'],
        'offline_owned_dwarf':offline_fixture()==old['offline_owned_dwarf'],
        'quest_layout':current_quest==old['original_quest_log'],
        'native_quests':saved_quests(1)==old['original_native_quests'],
        'same_session':actors.session_entry(t.fixture)['session']==old['session'],
        'group':state['group']==old['original_group'],
        'panels_closed':not state.get('panels') and not state.get('bags'),
        'chat_closed':not state.get('chat_edit_open'),'no_lua_errors':not state.get('lua_errors'),
        'no_blocked_actions':not state.get('blocked_actions')}
    t.receipt['friend_restoration']={'checks':checks};t.persist()
    if not all(checks.values()):raise RuntimeError('friend trial did not restore its original fixture')


def recovery_source_matches(old,current):
    pending=old.get('chat_submission_checks',[{}])[-1]
    outcomes=[r for r in old.get('cases',[]) if r.get('status')=='friend_status_pass']
    failed=old.get('cases',[{}])[-1]
    return (old.get('completed') is False and bool(old.get('finished_at')) and
        old.get('failure')=='RuntimeError: panel cleanup did not change state; refusing to replay Escape' and
        old.get('actor')==current.get('actor') and old.get('runtime')==current.get('runtime') and
        old.get('actor',{}).get('guid')==1 and
        [r.get('id') for r in outcomes]==['friends.add_friend','friends.duplicate_friend_error',
            'friends.self_friend_error','friends.nonexistent_friend_error'] and
        all(r.get('oracle',{}).get('checks') and all(r['oracle']['checks'].values()) for r in outcomes) and
        failed.get('id')=='friends.remove_friend' and failed.get('status')=='infrastructure_failure' and
        failed.get('error')=='RuntimeError: chat edit differs from the selected command; refusing submission' and
        pending.get('submitted') is False and pending.get('selected_text')=='/removefriend '+FRIEND and
        pending.get('observed_text')=='/removefriend '+REMOVE_NAME and pending.get('observed_focused') is True)


def menu_recovery_source_matches(old,current):
    cases=old.get('cases') or [];last=cases[-1] if cases else {}
    checks=last.get('oracle',{}).get('checks',{})
    bad={'exact_modern_request','exact_native_request','exact_native_status','exact_modern_status',
        'native_social','public_friends'}
    good={'ordinary_input','friends_ready','stock_window','dialog_closed','chat_closed','clean'}
    return (old.get('completed') is False and bool(old.get('finished_at')) and
        old.get('failure')=='RuntimeError: operation did not advance: fixture.friends.recovery_remove client_or_protocol_failure' and
        old.get('actor')==current.get('actor') and old.get('runtime')==current.get('runtime') and
        old.get('actor',{}).get('guid')==1 and old.get('source_preflight') and
        all(old['source_preflight'].values()) and
        [(r.get('id'),r.get('status')) for r in cases]==[('fixture.friends.close','friend_window_closed'),
            ('fixture.friends.recovery_open','friend_window_open'),
            ('fixture.friends.recovery_remove','client_or_protocol_failure')] and
        last.get('input')=={'kind':'chat','value':'/removefriend '+REMOVE_NAME} and
        last.get('oracle',{}).get('packets')==[] and set(checks)==bad|good and
        all(checks[k] is False for k in bad) and all(checks[k] is True for k in good))


def recover(t,path):
    path=path.resolve()
    if path.name!='episode.json' or not path.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('requires a closed owned friend removal failure')
    old=json.loads(path.read_text());retry=menu_recovery_source_matches(old,t.receipt)
    if retry:
        parent=Path(old['source']['path']).resolve()
        if (parent.name!='episode.json' or not parent.is_relative_to(lab.ROOT/'evidence') or
                lab.sha256(parent)!=old['source']['sha256']):
            raise RuntimeError('failed removal recovery parent changed')
        old=json.loads(parent.read_text())
    if not recovery_source_matches(old,t.receipt):raise RuntimeError('friend cleanup source or owned lifetime differs')
    expected=sorted(old['original_social']+[[1,GUID,1,'']],key=lambda r:(r[0],r[1]))
    native=canonical(capture(t));base=old['native_baseline']
    state,quest=quest_detail(t,'friends_recovery_guard')
    checks={'exact_prepared_social':social()==expected,
        'native_state':all(native[k]==base[k] for k in base if k!='afk'),
        'inventory_money':canonical(inventory())==old['original_inventory'],
        'quest_layout':quest==old['original_quest_log'],'native_quests':saved_quests(1)==old['original_native_quests'],
        'offline_owned_dwarf':offline_fixture()==old['offline_owned_dwarf'],
        'same_session':actors.session_entry(t.fixture)['session']==old['session'],
        'exact_chat_layout':(not state.get('chat_edit_open') and 'FriendsFrame' in state['panels'] if retry else
            state.get('chat_edit_open') is True and state.get('chat_edit_focused') is True and
            state.get('chat_edit_text')=='/removefriend '+REMOVE_NAME),
        'group':state['group']==old['original_group'],'clean':not state.get('lua_errors') and not state.get('blocked_actions')}
    t.receipt.update(source={'path':str(path),'sha256':lab.sha256(path)},source_preflight=checks,
        original_source={'path':str(parent) if retry else str(path),'sha256':lab.sha256(parent) if retry else lab.sha256(path)},
        qualified_scope='Cleanup only. Cancel the exact unsubmitted autocomplete edit and remove only the source-bound dwarf friend. No gameplay qualification.',
        custom_script_permission='blocked_by_user',softTargetInteract=old['softTargetInteract']);t.persist()
    if not all(checks.values()):raise RuntimeError('source-bound friend cleanup fixture differs')
    close_friends(t);open_friends(t,'fixture.friends.recovery_open')
    operation(t,Packets(old['session']),'fixture.friends.recovery_remove',FRIEND,GUID,5,
        old['original_social'],old['original_public_friends'],remove=True)
    close_friends(t);restored(t,old)


def suite(t):
    if t.fixture['guid']!=1:raise RuntimeError('requires the owned primary warrior')
    session=actors.session_entry(t.fixture)['session'];t.clean_panels()
    state,quest=quest_detail(t,'friends_original_quest')
    if state.get('target',{}).get('exists') or state.get('observer_version')!=122:
        raise RuntimeError('requires observer122 and no original target')
    native=canonical(capture(t));lab.server_command('saveall');time.sleep(1)
    original=social();original_inventory=canonical(inventory());dwarf=offline_fixture();quests=saved_quests(1)
    expected=sorted(original+[[1,GUID,1,'']],key=lambda r:(r[0],r[1]))
    if any(r[0]==1 and r[1]==GUID for r in original):
        raise RuntimeError('the disposable dwarf already has a social row')
    original_public=public(state.get('friends'))
    if original_public!=[{'name':'Harnesstwo','connected':False,'level':0,'notes':''}]:
        raise RuntimeError('requires the preserved original one-offline-friend public list')
    added_public=original_public+[{'name':FRIEND,'connected':False,'level':0,'notes':''}]
    t.receipt.update(native_baseline=native,original_social=original,original_public_friends=original_public,
        original_inventory=original_inventory,original_quest_log=quest,original_native_quests=quests,
        original_group=state['group'],offline_owned_dwarf=dwarf,session=session,
        custom_script_permission='blocked_by_user',
        softTargetInteract={'original':'0','current_stock_disabled':'1','original_restored':False},
        qualified_scope='Owned offline dwarf addition/removal and exact self/nonexistent/duplicate stock friend errors. '
            'Other social, online-presence, note and persistence variants remain open.');t.persist()
    packets=Packets(session)
    try:
        open_friends(t,'fixture.friends.open')
        operation(t,packets,'friends.add_friend',FRIEND,GUID,7,expected,added_public)
        operation(t,packets,'friends.duplicate_friend_error',FRIEND,GUID,8,expected,added_public)
        operation(t,packets,'friends.self_friend_error','Harnessone',1,9,expected,added_public)
        operation(t,packets,'friends.nonexistent_friend_error',MISSING,0,4,expected,added_public)
        operation(t,packets,'friends.remove_friend',FRIEND,GUID,5,original,original_public,remove=True)
    finally:
        close_friends(t);current=social()
        if current!=original:
            if current!=expected:raise RuntimeError('social cleanup differs from the exact prepared row; refusing mutation')
            open_friends(t,'fixture.friends.cleanup_open')
            operation(t,packets,'fixture.friends.cleanup_remove',FRIEND,GUID,5,original,original_public,remove=True)
            close_friends(t)
        restored(t,t.receipt)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--source',type=Path);a=p.parse_args()
    with actor('primary'):
        t=Trial(a.output,controller='code')
        try:
            (recover(t,a.source) if a.source else suite(t));t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:
            t.receipt['finished_at']=time.time();t.persist()
            print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure')}),flush=True)


if __name__=='__main__':main()
