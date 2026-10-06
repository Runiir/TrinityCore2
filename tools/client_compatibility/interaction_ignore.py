"""Add and remove only the owned offline dwarf through the stock Ignore UI."""
import argparse,json,re,struct,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_trial import Trial
from .interaction_social import actor
from .interaction_friend_notes import baseline,dialog_identity
from .interaction_friends import social,public,open_friends,close_friends,restored,FRIEND,GUID,HIGH
from .interaction_control_target import click,edit
from .interaction_operations import controls
from .interaction_macros import require
from .interaction_lifecycle import Packets
from .world.buffer import Reader

CONTEXT='Enter name of player to ignore\nor\nShift-Click a name from th'


def wire_checks(rows,remove=False):
    op='CMSG_DEL_IGNORE' if remove else 'CMSG_ADD_IGNORE';result=16 if remove else 15
    def bodies(name,direction):
        return [bytes.fromhex(r['body']) for r in rows if r['name']==name and r['direction']==direction]
    requests=[]
    for body in bodies(op,'from_client'):
        r=Reader(body)
        if remove:requests.append((r.unpack('I')[0],r.guid()))
        else:
            length=r.bits(9);account=r.guid();requests.append((r.raw(length).decode(),account))
        r.end()
    responses=[]
    for body in bodies('SMSG_FRIEND_STATUS','to_client'):
        r=Reader(body);status=r.unpack('B')[0];player=r.guid();account=r.guid()
        realm,connected,area,level,klass=r.unpack('IBIII');length=r.bits(10);note=r.raw(length).decode();r.end()
        responses.append((status,player,account,realm,connected,area,level,klass,note))
    return {'exact_modern_request':requests==[(1,(GUID,HIGH)) if remove else (FRIEND,(0,0))],
        'exact_native_request':bodies(op,'to_native')==[struct.pack('<Q',GUID) if remove else FRIEND.encode()+b'\0'],
        'exact_native_status':bodies('SMSG_FRIEND_STATUS','from_native')==[struct.pack('<BQ',result,GUID)],
        'exact_modern_status':responses==[(result,(GUID,HIGH),(0,0),1,0,0,0,0,'')]}


def ignore_rows(rows):
    return [c for c in rows if re.fullmatch(r'FriendsFrameIgnoreButton\d+',c['name']) and
        c['kind']=='Button' and c['text']]


def ignore_tab(t,label):
    def outcome(b,a,s):
        rows=controls(t);state,frame=t.observe(label.replace('.','_')+'_rendered')
        checks={'ordinary_input':bool(s),'stock_friends':'FriendsFrame' in a['panels'],
            'ignore_add_control':any(c['name']=='FriendsFrameIgnorePlayerButton' and c['enabled'] for c in rows),
            'ignore_remove_control':any(c['name']=='FriendsFrameUnsquelchButton' for c in rows)}
        t.receipt.setdefault('ignore_tabs',[]).append({'checks':checks,'controls':rows,'state':state,'frame':frame})
        t.persist()
        return {'status':'ignore_tab_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks}}
    require(click(t,label,'Select the observed stock Ignore tab.',
        lambda c:c['name']=='FriendsTabHeaderTab2' and c['text']=='Ignore',outcome),'ignore_tab_pass')


def add_dialog(t,label):
    require(click(t,label,'Open the stock Ignore Player name dialog.',
        lambda c:c['name']=='FriendsFrameIgnorePlayerButton',lambda b,a,s:
        {'status':'ignore_dialog_open' if s and 'StaticPopup1' in a['panels'] else
            'client_or_protocol_failure'},await_state=lambda a:'StaticPopup1' in a['panels']),
        'ignore_dialog_open')
    rows=controls(t);state,frame=t.observe(label.replace('.','_')+'_rendered')
    contract=[c for c in rows if c['name'].startswith('StaticPopup1')]
    t.receipt.setdefault('ignore_dialogs',[]).append({'controls':contract,'state':state,'frame':frame})
    t.persist();return contract


def cleanup(t):
    state,_=t.observe('ignore_cleanup_guard')
    if 'StaticPopup1' in state['panels']:
        require(click(t,'fixture.ignore.cancel','Cancel the observed Ignore Player dialog.',
            lambda c:c['name']=='StaticPopup1Button2' and c['text']=='Cancel',lambda b,a,s:
            {'status':'ignore_dialog_cancelled' if s and 'StaticPopup1' not in a['panels'] else
                'client_or_protocol_failure'},await_state=lambda a:'StaticPopup1' not in a['panels']),
            'ignore_dialog_cancelled')
    if 'FriendsFrame' in state['panels']:
        require(click(t,'fixture.ignore.friends_tab','Restore the stock Friends subtab before closing.',
            lambda c:c['name']=='FriendsTabHeaderTab1' and c['text']=='Friends',lambda b,a,s:
            {'status':'friend_tab_restored' if s and any(c['name']=='FriendsFrameAddFriendButton'
                for c in controls(t)) else 'client_or_protocol_failure'}),'friend_tab_restored')
    close_friends(t)


def probe(t,observer_version=122):
    baseline(t,observer_version);t.receipt['qualified_scope']='Stock Ignore tab and name-dialog inspection/cancel only; no gameplay qualification.'
    t.persist()
    try:
        open_friends(t,'fixture.ignore.open');ignore_tab(t,'fixture.ignore.tab')
        rows=ignore_rows(t.receipt['ignore_tabs'][-1]['controls'])
        if rows or social()!=t.receipt['original_social']:
            raise RuntimeError('requires the preserved empty stock Ignore list')
        add_dialog(t,'fixture.ignore.dialog')
    finally:cleanup(t);restored(t,t.receipt)


def source_matches(old,current):
    expected=[('StaticPopup1Button1','Button','Accept',CONTEXT),
        ('StaticPopup1Button2','Button','Cancel',CONTEXT),('StaticPopup1EditBox','EditBox','',CONTEXT)]
    return (old.get('completed') is True and old.get('failure') is None and bool(old.get('finished_at')) and
        old.get('actor')==current.get('actor') and old.get('runtime')==current.get('runtime') and
        old.get('original_social')==[[1,2,1,''],[2,1,1,'']] and len(old.get('ignore_dialogs',[]))==1 and
        dialog_identity(old['ignore_dialogs'][0]['controls'])==expected and
        all(c['enabled'] for c in old['ignore_dialogs'][0]['controls']) and
        len(old.get('ignore_tabs',[]))==1 and not ignore_rows(old['ignore_tabs'][0]['controls']) and
        all(old.get(k,{}).get('checks') and all(old[k]['checks'].values()) for k in
            ('bridge_native_restoration','friend_restoration')))


def operation(t,packets,label,source,remove=False):
    if not remove:
        contract=add_dialog(t,label+'.dialog')
        if dialog_identity(contract)!=dialog_identity(source['ignore_dialogs'][0]['controls']):
            raise RuntimeError('fresh Ignore dialog differs from the reviewed owned probe')
        require(edit(t,label+'.name','Enter only the exact owned offline dwarf name.',
            lambda c:c['name']=='StaticPopup1EditBox' and c.get('context')==CONTEXT,FRIEND),'ui_edit_pass')
    else:
        rows=ignore_rows(controls(t))
        if len(rows)!=1 or rows[0]['text'] not in (FRIEND,FRIEND+'-Client442Lab'):
            raise RuntimeError('requires only the exact owned dwarf in the stock Ignore list')
        selected=rows[0]
        require(click(t,label+'.select','Select only the owned ignored dwarf row.',
            lambda c:c['name']==selected['name'] and c['text']==selected['text'],lambda b,a,s:
            {'status':'ignore_row_selected' if s and any(c['name']=='FriendsFrameUnsquelchButton' and
                c['enabled'] for c in controls(t)) else 'client_or_protocol_failure'}),'ignore_row_selected')
    started=time.time();expected=(t.receipt['original_social'] if remove else
        sorted(t.receipt['original_social']+[[1,GUID,2,'']],key=lambda r:(r[0],r[1])))
    def outcome(b,a,s):
        trace=[r for r in packets.since(started) if r['name'] in
            ('CMSG_ADD_IGNORE','CMSG_DEL_IGNORE','SMSG_FRIEND_STATUS')]
        visible=ignore_rows(controls(t));checks=wire_checks(trace,remove)
        checks.update(ordinary_input=bool(s),native_social=social()==expected,
            public_friends_preserved=public(a.get('friends'))==t.receipt['original_public_friends'],
            stock_ignore_rows=(not visible if remove else len(visible)==1 and
                visible[0]['text'] in (FRIEND,FRIEND+'-Client442Lab')),
            stock_window='FriendsFrame' in a['panels'],dialog_closed='StaticPopup1' not in a['panels'],
            chat_closed=not a.get('chat_edit_open'),clean=not a.get('lua_errors') and not a.get('blocked_actions'))
        return {'status':'ignore_status_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'packets':trace,'ignore_rows':visible}}
    predicate=(lambda c:c['name']=='FriendsFrameUnsquelchButton' and c['text']=='Remove Player') if remove else (
        lambda c:c['name']=='StaticPopup1Button1' and c['text']=='Accept' and c.get('context')==CONTEXT)
    require(click(t,label,'Remove only the selected owned ignored dwarf.' if remove else
        'Accept only the owned offline dwarf Ignore request.',predicate,outcome),'ignore_status_pass')
    state,frame=t.observe(label.replace('.','_')+'_rendered')
    t.receipt.setdefault('ignore_rendered',[]).append({'case':label,'state':state,'frame':frame});t.persist()


def suite(t,path,observer_version=122):
    path=path.resolve()
    if path.name!='episode.json' or not path.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('requires a closed owned Ignore dialog probe')
    old=json.loads(path.read_text())
    if not source_matches(old,t.receipt):raise RuntimeError('owned Ignore probe verdict, actor or runtime differs')
    t.receipt['source']={'path':str(path),'sha256':lab.sha256(path)};t.persist()
    baseline(t,observer_version);packets=Packets(t.receipt['session'])
    t.receipt['qualified_scope']='Owned offline dwarf Ignore addition/removal through stock name dialog, row selection and Remove Player. No ignored-chat, persistence or other social qualification.'
    t.persist()
    try:
        open_friends(t,'fixture.ignore.open');ignore_tab(t,'fixture.ignore.tab')
        if ignore_rows(t.receipt['ignore_tabs'][-1]['controls']):raise RuntimeError('original stock Ignore list is not empty')
        operation(t,packets,'friends.add_ignore',old);operation(t,packets,'friends.remove_ignore',old,remove=True)
    finally:
        state,_=t.observe('ignore_final_guard')
        if 'StaticPopup1' in state['panels']:
            require(click(t,'fixture.ignore.pending_cancel','Cancel the owned pending Ignore dialog.',
                lambda c:c['name']=='StaticPopup1Button2' and c['text']=='Cancel',lambda b,a,s:
                {'status':'ignore_dialog_cancelled' if s and 'StaticPopup1' not in a['panels'] else
                    'client_or_protocol_failure'}),'ignore_dialog_cancelled')
        current=social();prepared=sorted(t.receipt['original_social']+[[1,GUID,2,'']],key=lambda r:(r[0],r[1]))
        if current!=t.receipt['original_social']:
            if current!=prepared:raise RuntimeError('Ignore cleanup refuses unrelated social changes')
            operation(t,packets,'fixture.ignore.restore',old,remove=True)
        rows=controls(t);empty=not ignore_rows(rows) and any(c['name']=='FriendsFrameIgnorePlayerButton' for c in rows)
        t.receipt['ignore_restoration']={'checks':{'native_social':social()==t.receipt['original_social'],
            'stock_ignore_empty':empty},'controls':rows};t.persist()
        cleanup(t);restored(t,t.receipt)
        if not all(t.receipt['ignore_restoration']['checks'].values()):
            raise RuntimeError('stock or native Ignore list did not restore')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--source-probe',type=Path)
    p.add_argument('--observer-version',type=int,choices=[122,123],default=122);a=p.parse_args()
    with actor('primary'):
        t=Trial(a.output,controller='code')
        try:
            (suite(t,a.source_probe,a.observer_version) if a.source_probe else probe(t,a.observer_version));t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:
            t.receipt['finished_at']=time.time();t.persist()
            print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure')}),flush=True)


if __name__=='__main__':main()
