"""Edit and restore a note through the observed stock owned-friend dialog."""
import argparse,json,struct,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_social import actor
from .interaction_friends import (canonical,social,public,offline_fixture,open_friends,close_friends,restored,HIGH)
from .interaction_control_target import target,click,edit
from .interaction_chat_player_actions import menu_click
from .interaction_operations import controls,point
from .interaction_macros import require
from .interaction_bridge_restoration import capture
from .interaction_quest_link import detail as quest_detail,saved as saved_quests
from .interaction_trade import inventory
from .interaction_lifecycle import Packets
from .world.buffer import Reader

FRIEND='Harnesstwo'
GUID=2
NOTE='Owned offline scout note UI101'
CONTEXT='Set Notes for Harnesstwo:'


def wire_checks(rows,note):
    requests=[];native=[]
    for row in rows:
        if row['name']!='CMSG_SET_CONTACT_NOTES':continue
        body=bytes.fromhex(row['body'])
        if row['direction']=='from_client':
            r=Reader(body);realm=r.unpack('I')[0];guid=r.guid();length=r.bits(10)
            requests.append((realm,guid,r.raw(length).decode()));r.end()
        elif row['direction']=='to_native':native.append(body)
    return {'exact_modern_request':requests==[(1,(GUID,HIGH),note)],
        'exact_native_request':native==[struct.pack('<Q',GUID)+note.encode()+b'\0']}


def baseline(t,observer_version=122):
    if t.fixture['guid']!=1:raise RuntimeError('requires the owned primary warrior')
    t.clean_panels();state,quest=quest_detail(t,'friend_note_original_quest')
    if state.get('observer_version')!=observer_version or state.get('target',{}).get('exists'):
        raise RuntimeError('requires the specified observer version and no original target')
    lab.server_command('saveall');time.sleep(1)
    rows=social();original_public=public(state.get('friends'))
    if rows!=[[1,2,1,''],[2,1,1,'']] or original_public!=[
            {'name':FRIEND,'connected':False,'level':0,'notes':''}]:
        raise RuntimeError('requires the exact original reciprocal offline friend rows without notes')
    t.receipt.update(native_baseline=canonical(capture(t)),original_social=rows,
        original_public_friends=original_public,original_inventory=canonical(inventory()),
        original_quest_log=quest,original_native_quests=saved_quests(1),original_group=state['group'],
        offline_owned_dwarf=offline_fixture(),session=actors.session_entry(t.fixture)['session'],
        custom_script_permission='blocked_by_user',
        softTargetInteract={'original':'0','current_stock_disabled':'1','original_restored':False});t.persist()


def note_dialog(t,label):
    row=target(t,label+'.row',lambda c:c['kind']=='Button' and
        c['name'].startswith('FriendsFrameFriendsScrollFrameButton') and c['text']==FRIEND)
    expected=social()
    def menu(b,a,s):
        rows=controls(t);state,frame=t.observe(label.replace('.','_')+'_menu')
        matches=[c for c in rows if c['text']=='Set Note' and c['enabled'] and c['kind'] in ('Button','MenuItem')]
        checks={'owned_row':row['text']==FRIEND,'ordinary_right_click':s=='menu',
            'stock_menu':any(p in a['panels'] for p in ('ContextMenu','DropDownList1')),
            'one_set_note_control':len(matches)==1,'social_unchanged':social()==expected}
        t.receipt.setdefault('friend_note_menus',[]).append({'checks':checks,'row':row,
            'controls':rows,'state':state,'frame':frame});t.persist()
        return {'status':'friend_note_menu_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks}}
    require(t.step(label+'.menu','Open the exact original owned scout friend-row menu.',
        {'menu':{'kind':'click','value':point(row),'button':3,'hold':.4}},menu,
        diagnostic_action='menu'),'friend_note_menu_pass')
    require(menu_click(t,label+'.dialog','Set Note',lambda b,a,s:
        {'status':'friend_note_dialog_open' if s and 'StaticPopup1' in a['panels'] and social()==expected
            else 'client_or_protocol_failure'},await_state=lambda a:'StaticPopup1' in a['panels']),
        'friend_note_dialog_open')
    rows=controls(t);state,frame=t.observe(label.replace('.','_')+'_dialog')
    contract=[c for c in rows if c['name'].startswith('StaticPopup1')]
    t.receipt.setdefault('friend_note_dialogs',[]).append({'controls':contract,'state':state,'frame':frame})
    t.persist();return contract


def cancel_dialog(t):
    state,_=t.observe('friend_note_cancel_guard')
    if 'StaticPopup1' in state['panels']:
        require(click(t,'fixture.friend_note.cancel','Cancel the observed stock friend note dialog.',
            lambda c:c['name']=='StaticPopup1Button2' and c['text']=='Cancel',lambda b,a,s:
            {'status':'friend_note_dialog_cancelled' if s and 'StaticPopup1' not in a['panels']
                else 'client_or_protocol_failure'},await_state=lambda a:'StaticPopup1' not in a['panels']),
            'friend_note_dialog_cancelled')


def probe(t,observer_version=122):
    baseline(t,observer_version)
    t.receipt['qualified_scope']='Stock owned-friend note dialog reconnaissance and cancellation only; no gameplay qualification.'
    t.persist()
    try:
        open_friends(t,'fixture.friend_note.open');note_dialog(t,'fixture.friend_note.probe')
    finally:
        cancel_dialog(t);close_friends(t);restored(t,t.receipt)


def dialog_identity(rows):
    return sorted((c['name'],c['kind'],c['text'] if c['kind']!='EditBox' else '',c.get('context')) for c in rows)


def source_matches(old,current):
    expected=[('StaticPopup1Button1','Button','Accept',CONTEXT),
        ('StaticPopup1Button2','Button','Cancel',CONTEXT),('StaticPopup1EditBox','EditBox','',CONTEXT)]
    return (old.get('completed') is True and old.get('failure') is None and bool(old.get('finished_at')) and
        old.get('actor')==current.get('actor') and old.get('runtime')==current.get('runtime') and
        old.get('original_social')==[[1,2,1,''],[2,1,1,'']] and len(old.get('friend_note_dialogs',[]))==1 and
        dialog_identity(old['friend_note_dialogs'][0]['controls'])==expected and
        all(c['enabled'] for c in old['friend_note_dialogs'][0]['controls']) and
        all(old.get(k,{}).get('checks') and all(old[k]['checks'].values()) for k in
            ('bridge_native_restoration','friend_restoration')))


def set_note(t,packets,label,note,source):
    contract=note_dialog(t,label)
    if dialog_identity(contract)!=dialog_identity(source['friend_note_dialogs'][0]['controls']):
        raise RuntimeError('fresh friend note dialog differs from the reviewed owned probe')
    require(edit(t,label+'.text','Enter the exact short owned friend note.',
        lambda c:c['name']=='StaticPopup1EditBox' and c.get('context')==CONTEXT,note),'ui_edit_pass')
    state,frame=t.observe(label.replace('.','_')+'_pending')
    t.receipt.setdefault('friend_note_pending',[]).append({'case':label,'note':note,'state':state,'frame':frame})
    t.persist();started=time.time()
    expected=[[1,2,1,note],[2,1,1,'']]
    def outcome(b,a,s):
        rows=[r for r in packets.since(started) if r['name']=='CMSG_SET_CONTACT_NOTES']
        checks=wire_checks(rows,note)
        checks.update(ordinary_input=bool(s),native_social=social()==expected,
            public_friends=public(a.get('friends'))==[{'name':FRIEND,'connected':False,'level':0,'notes':note}],
            friends_ready=a.get('friends_ready') is True,stock_window='FriendsFrame' in a['panels'],
            dialog_closed='StaticPopup1' not in a['panels'],chat_closed=not a.get('chat_edit_open'),
            clean=not a.get('lua_errors') and not a.get('blocked_actions'))
        return {'status':'friend_note_edit_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'packets':rows,'native_has_no_note_acknowledgement':True}}
    require(click(t,label,'Accept the exact owned friend note.',lambda c:c['name']=='StaticPopup1Button1' and
        c['text']=='Accept' and c.get('context')==CONTEXT,outcome,
        await_state=lambda a:'StaticPopup1' not in a['panels'] and
            any(f['name']==FRIEND and f['notes']==note for f in a.get('friends') or [])),'friend_note_edit_pass')
    row=target(t,label+'.hover',lambda c:c['kind']=='Button' and
        c['name'].startswith('FriendsFrameFriendsScrollFrameButton') and c['text']==FRIEND)
    t.execute({'kind':'hover','value':point(row)});time.sleep(1)
    state,frame=t.observe(label.replace('.','_')+'_rendered')
    t.receipt.setdefault('friend_note_rendered',[]).append({'case':label,'note':note,'state':state,'frame':frame})
    t.persist();t.execute({'kind':'hover','value':[1000,360]})


def suite(t,path,observer_version=122):
    path=path.resolve()
    if path.name!='episode.json' or not path.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('requires a closed owned note dialog probe')
    old=json.loads(path.read_text())
    if not source_matches(old,t.receipt):raise RuntimeError('owned note probe verdict, actor or runtime differs')
    t.receipt['source']={'path':str(path),'sha256':lab.sha256(path)};t.persist()
    baseline(t,observer_version);packets=Packets(t.receipt['session'])
    t.receipt['qualified_scope']='One short ASCII note on the original owned offline scout friend, then empty-note restoration through stock controls. No persistence or other social qualification.'
    t.persist()
    try:
        open_friends(t,'fixture.friend_note.open');set_note(t,packets,'friends.note_edit',NOTE,old)
    finally:
        cancel_dialog(t);current=social()
        if current!=t.receipt['original_social']:
            if current!=[[1,2,1,NOTE],[2,1,1,'']]:
                raise RuntimeError('friend note cleanup refuses any unrelated social change')
            state,_=t.observe('friend_note_restore_guard')
            if 'FriendsFrame' not in state['panels']:open_friends(t,'fixture.friend_note.restore_open')
            set_note(t,packets,'fixture.friend_note.restore','',old)
        close_friends(t);restored(t,t.receipt)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--source-probe',type=Path);p.add_argument('--observer-version',type=int,choices=[122,123],default=122);a=p.parse_args()
    with actor('primary'):
        t=Trial(a.output,controller='code')
        try:
            (suite(t,a.source_probe,a.observer_version) if a.source_probe else probe(t,a.observer_version));t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:
            t.receipt['finished_at']=time.time();t.persist()
            print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure')}),flush=True)


if __name__=='__main__':main()
