"""Temporarily ignore only the existing owned online friend, preserving friendship."""
import time
from .interaction_ignore import (CONTEXT,add_dialog,ignore_rows,ignore_tab,cleanup,
    source_matches,wire_checks)
from .interaction_friend_notes import dialog_identity
from .interaction_friend_presence import public_presence_matches
from .interaction_friends import social,open_friends
from .interaction_control_target import click,edit
from .interaction_operations import controls
from .interaction_macros import require

NAME='Harnesstwo'
GUID=2
ORIGINAL=[[1,2,1,''],[2,1,1,'']]
IGNORED=[[1,2,3,''],[2,1,1,'']]


def current_matches(rows,remove):
    return rows==(IGNORED if remove else ORIGINAL)


def mutation(t,packets,label,probe,remove=False):
    if not source_matches(probe,t.receipt) or t.receipt['original_social']!=ORIGINAL:
        raise RuntimeError('current owned empty Ignore probe differs')
    state,_=t.observe(label.replace('.','_')+'_guard')
    if not current_matches(social(),remove) or not public_presence_matches(state.get('friends'),True):
        raise RuntimeError('owned online friend or exact social flags differ')
    if not remove:
        contract=add_dialog(t,label+'.dialog')
        if dialog_identity(contract)!=dialog_identity(probe['ignore_dialogs'][0]['controls']):
            raise RuntimeError('fresh owned Ignore dialog differs')
        require(edit(t,label+'.name','Enter only the existing owned friend name.',
            lambda c:c['name']=='StaticPopup1EditBox' and c.get('context')==CONTEXT,NAME),'ui_edit_pass')
    else:
        rows=ignore_rows(controls(t))
        if len(rows)!=1 or rows[0]['text'] not in (NAME,NAME+'-Client442Lab'):
            raise RuntimeError('stock Ignore row is not exactly the owned friend')
        row=rows[0]
        require(click(t,label+'.select','Select only the owned ignored friend.',
            lambda c:c['name']==row['name'] and c['text']==row['text'],lambda b,a,s:
            {'status':'ignore_row_selected' if s and any(c['name']=='FriendsFrameUnsquelchButton' and
                c['enabled'] for c in controls(t)) else 'client_or_protocol_failure'}),'ignore_row_selected')
    started=time.time()
    def outcome(b,a,selected):
        trace=[r for r in packets.since(started) if r['name'] in
            ('CMSG_ADD_IGNORE','CMSG_DEL_IGNORE','SMSG_FRIEND_STATUS')]
        rows=ignore_rows(controls(t));checks=wire_checks(trace,remove,guid=GUID,name=NAME)
        checks.update(ordinary_input=bool(selected),native_social=current_matches(social(),not remove),
            public_friends_preserved=public_presence_matches(a.get('friends'),True),
            stock_ignore_rows=(not rows if remove else len(rows)==1 and
                rows[0]['text'] in (NAME,NAME+'-Client442Lab')),
            dialog_closed='StaticPopup1' not in a['panels'],chat_closed=not a.get('chat_edit_open'),
            no_lua_errors=not a.get('lua_errors'),no_blocked_actions=not a.get('blocked_actions'))
        return {'status':'ignore_status_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'packets':trace,'ignore_rows':rows}}
    predicate=(lambda c:c['name']=='FriendsFrameUnsquelchButton' and c['text']=='Remove Player') if remove else (
        lambda c:c['name']=='StaticPopup1Button1' and c['text']=='Accept' and c.get('context')==CONTEXT)
    require(click(t,label,'Remove only the selected owned Ignore flag.' if remove else
        'Accept only the owned friend Ignore request.',predicate,outcome),'ignore_status_pass')


def restore_ignore(t,packets,probe):
    state,_=t.observe('ignored_chat_cleanup_guard')
    if 'StaticPopup1' in state['panels']:
        require(click(t,'fixture.ignored_chat.cancel','Cancel only the stock owned Ignore dialog.',
            lambda c:c['name']=='StaticPopup1Button2' and c['text']=='Cancel' and c.get('context')==CONTEXT,
            lambda b,a,s:{'status':'ignore_dialog_cancelled' if s and 'StaticPopup1' not in a['panels'] else
                'client_or_protocol_failure'}),'ignore_dialog_cancelled')
    if social()==IGNORED:
        if 'FriendsFrame' not in state['panels']:open_friends(t,'fixture.ignored_chat.cleanup_open')
        ignore_tab(t,'fixture.ignored_chat.cleanup_tab')
        mutation(t,packets,'fixture.ignored_chat.restore',probe,remove=True)
    elif social()!=ORIGINAL:raise RuntimeError('ignore cleanup refuses unrelated social changes')
    ignore_tab(t,'fixture.ignored_chat.empty_tab');rows=controls(t)
    state,frame=t.observe('ignored_chat_restored')
    checks={'native_social':social()==ORIGINAL,'public_friends_preserved':public_presence_matches(state.get('friends'),True),
        'stock_ignore_empty':not ignore_rows(rows) and any(c['name']=='FriendsFrameIgnorePlayerButton' for c in rows)}
    t.receipt['ignored_chat_restoration']={'checks':checks,'frame':frame};t.persist()
    cleanup(t);open_friends(t,'fixture.ignored_chat.friend_tab_restored')
    if not all(checks.values()):raise RuntimeError('owned Ignore flag or stock list did not restore')
