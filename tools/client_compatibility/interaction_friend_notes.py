"""Inspect the stock note dialog for one original owned offline friend."""
import argparse,json,struct,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_social import actor
from .interaction_friends import (canonical,social,public,offline_fixture,open_friends,close_friends,restored,HIGH)
from .interaction_control_target import target,click
from .interaction_chat_player_actions import menu_click
from .interaction_operations import controls,point
from .interaction_macros import require
from .interaction_bridge_restoration import capture
from .interaction_quest_link import detail as quest_detail,saved as saved_quests
from .interaction_trade import inventory
from .world.buffer import Reader

FRIEND='Harnesstwo'
GUID=2
NOTE='Owned offline scout note UI101'


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


def baseline(t):
    if t.fixture['guid']!=1:raise RuntimeError('requires the owned primary warrior')
    t.clean_panels();state,quest=quest_detail(t,'friend_note_original_quest')
    if state.get('observer_version')!=122 or state.get('target',{}).get('exists'):
        raise RuntimeError('requires observer122 and no original target')
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


def probe(t):
    baseline(t)
    t.receipt['qualified_scope']='Stock owned-friend note dialog reconnaissance and cancellation only; no gameplay qualification.'
    t.persist()
    try:
        open_friends(t,'fixture.friend_note.open');note_dialog(t,'fixture.friend_note.probe')
    finally:
        cancel_dialog(t);close_friends(t);restored(t,t.receipt)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    with actor('primary'):
        t=Trial(a.output,controller='code')
        try:probe(t);t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:
            t.receipt['finished_at']=time.time();t.persist()
            print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure')}),flush=True)


if __name__=='__main__':main()
