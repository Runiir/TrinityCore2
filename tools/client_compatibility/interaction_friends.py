"""Add one owned offline friend, check stock errors, and restore the social rows."""
import argparse,json,struct,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_social import actor
from .interaction_control_target import click,edit
from .interaction_macros import require
from .interaction_bridge_restoration import capture,restore
from .interaction_quest_link import detail as quest_detail,saved as saved_quests
from .interaction_trade import inventory
from .interaction_lifecycle import Packets
from .world.buffer import Reader

FRIEND='Harnessdwarf'
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
    require(click(t,label,'Open the stock Friends window.',lambda c:c['name']=='SocialsMicroButton',
        lambda b,a,s:{'status':'friend_window_open' if s and 'FriendsFrame' in a['panels'] else
            'client_or_protocol_failure'},await_state=lambda s:'FriendsFrame' in s['panels']),
        'friend_window_open')


def add_dialog(t,name,label):
    require(click(t,label+'.dialog','Open the stock character Add Friend dialog.',
        lambda c:c['name']=='FriendsFrameAddFriendButton',lambda b,a,s:{'status':'friend_dialog_open' if s and
            'StaticPopup1' in a['panels'] else 'client_or_protocol_failure'}),'friend_dialog_open')
    require(edit(t,label+'.name','Enter the exact owned or verified missing character name.',
        lambda c:c['name']=='StaticPopup1EditBox',name),'ui_edit_pass')


def operation(t,packets,label,name,guid,result,expected_rows,expected_public,remove=False):
    if not remove:add_dialog(t,name,label)
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
        require(t.step(label,'Remove only the disposable owned dwarf friend.',
            {'remove':{'kind':'chat','value':'/removefriend '+FRIEND}},outcome,diagnostic_action='remove',
            await_state=lambda s:not any(r['name']==FRIEND for r in s.get('friends') or [])),'friend_status_pass')
    else:
        require(click(t,label,'Confirm the stock Add Friend dialog.',lambda c:c['name']=='StaticPopup1Button1' and
            c['text']=='Add Friend',outcome,await_state=lambda s:'StaticPopup1' not in s['panels']),
            'friend_status_pass')
    state,frame=t.observe(label.replace('.','_')+'_rendered')
    t.receipt.setdefault('friend_rendered_outcomes',[]).append({'case':label,'name':name,'native_result':result,
        'state':state,'frame':frame});t.persist()


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
        t.clean_panels();current=social()
        if current!=original:
            if current!=expected:raise RuntimeError('social cleanup differs from the exact prepared row; refusing mutation')
            open_friends(t,'fixture.friends.cleanup_open')
            operation(t,packets,'fixture.friends.cleanup_remove',FRIEND,GUID,5,original,original_public,remove=True)
            t.clean_panels()
        restore(t,native)
        state,current_quest=quest_detail(t,'friends_restored')
        checks={'native_social':social()==original,'public_friends':public(state.get('friends'))==original_public,
            'inventory_money':canonical(inventory())==original_inventory,'offline_owned_dwarf':offline_fixture()==dwarf,
            'quest_layout':current_quest==quest,'native_quests':saved_quests(1)==quests,
            'same_session':actors.session_entry(t.fixture)['session']==session,'group':state['group']==t.receipt['original_group'],
            'panels_closed':not state.get('panels') and not state.get('bags'),
            'chat_closed':not state.get('chat_edit_open'),'no_lua_errors':not state.get('lua_errors'),
            'no_blocked_actions':not state.get('blocked_actions')}
        t.receipt['friend_restoration']={'checks':checks};t.persist()
        if not all(checks.values()):raise RuntimeError('friend trial did not restore its original fixture')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    with actor('primary'):
        t=Trial(a.output,controller='code')
        try:suite(t);t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:
            t.receipt['finished_at']=time.time();t.persist()
            print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure')}),flush=True)


if __name__=='__main__':main()
