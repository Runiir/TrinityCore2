"""Hide both equipped items, inspect normal character selection, and restore them.

Three closed phases require separate visual selection reviews before Return.
Only finish closes the complete visibility/persistence/restoration experiment.
"""
import argparse,hashlib,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_macros import edit_case,require
from .interaction_operations import point,click_case
from .interaction_settings_search import open_search
from .interaction_character_appearance import flags,toggle
from .interaction_bridge_deploy import identity,shot
from .interaction_lifecycle import Packets,request_logout
from .interaction_tooltips import baseline
from .interaction_equipment_set_roundtrip import stable
from .interaction_session_persist import public,close
from .observation.inventory import Inventory
from .observation.character_selection import characters
from .world.buffer import player_high


def saved_flags(t):
    lab.server_command('saveall')
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT characterFlags FROM client442_characters.characters WHERE guid=%s',(t.fixture['guid'],))
        row=q.fetchone()
    if row is None:raise RuntimeError('owned character row is absent')
    return row[0]


def source(t,path,phase):
    path=path.resolve()
    if not path.is_relative_to(lab.ROOT/'evidence') or path.name!='episode.json':raise ValueError('require owned source episode')
    old=json.loads(path.read_text())
    if (not old.get('completed') or not old.get('finished_at') or old.get('phase')!=phase or
        old['actor']!=t.fixture or old['runtime']!=t.receipt['runtime'] or
        stable(baseline())!=old['baseline']['native'] or saved_flags(t)!=old['pending_flags']):
        raise RuntimeError('source actor, runtime, resources or pending visibility differ')
    t.receipt.update(source={'file':str(path),'sha256':lab.sha256(path)},baseline=old['baseline'],
        native_session=old['native_session']);t.persist();return old


def settings(t,oracle,shown,search):
    field=open_search(t);predicate=lambda c:c['kind']=='EditBox' and point(c)==point(field)
    original=field['text'] if search is None else search
    t.receipt['search_original']=original;t.persist()
    for kind in ['helm','cloak']:
        require(edit_case(t,'session.find.'+kind,'Find the stock '+kind+' setting.',predicate,kind),'ui_edit_pass')
        require(toggle(t,oracle,kind,shown,'session.visibility.'+kind),'character_appearance_pass')
    require(edit_case(t,'session.restore_search','Restore the original stock settings search.',predicate,original),'ui_edit_pass')
    require(click_case(t,'session.close_settings','Close stock settings.',lambda c:c['text']=='Close',
        lambda b,a,s:{'status':'panel_closed_pass' if s and 'SettingsPanel' not in a['panels'] else 'client_or_protocol_failure'},
        await_state=lambda a:'SettingsPanel' not in a['panels']),'panel_closed_pass')
    t.clean_panels()


def logout(t,expected,label):
    packets=Packets(t.receipt['native_session']);started=request_logout(t,packets,label,False)
    deadline=time.monotonic()+32
    while not (packets.has(started,'SMSG_LOGOUT_COMPLETE','from_native') and
               packets.has(started,'SMSG_ENUM_CHARACTERS_RESULT','to_client')):
        if time.monotonic()>deadline:raise RuntimeError('normal logout/modern enumeration deadline exceeded')
        time.sleep(.2)
    row=next(r for r in packets.since(started) if r['name']=='SMSG_ENUM_CHARACTERS_RESULT' and r['direction']=='to_client')
    body=bytes.fromhex(row['body']);rows=characters(body);wanted=t.receipt['baseline']
    valid=(len(rows)==1 and rows[0]['guid']==[1,player_high()] and rows[0]['name']==t.fixture['character_name'] and
        rows[0]['flags']==expected and rows[0]['equipment']==wanted['public']['equipment'] and saved_flags(t)==expected)
    time.sleep(3);frame=shot(t.out/'character_selection.png')
    t.receipt.update(pending_flags=expected,character_selection=frame,
        enumeration={'time':row['time'],'session':row['session'],'body_sha256':hashlib.sha256(body).hexdigest(),'rows':rows})
    t.receipt['cases'].append({'id':'character.selection_visibility.'+label,'time':started,'frame':frame,
        'status':'character_selection_wire_pass' if valid else 'client_or_protocol_failure',
        'oracle':{'native_complete':True,'saved_flags':saved_flags(t),'modern_visibility_and_equipment':valid}});t.persist()
    if not valid:raise RuntimeError('modern selection visibility/equipment differs from the owned native fixture')


def enter(t,old,hidden):
    packets=Packets(old['native_session']);frame=shot(t.out/'reviewed_selection_before.png');started=time.time()
    t.execute({'kind':'key','value':'Return','hold':.4});time.sleep(8)
    state,after=t.observe('after_reentry');session=actors.session_entry(t.fixture)['session']
    oracle=Inventory(lab.ROOT,session,1).poll();expected=0xc00 if hidden else 0
    checks={'same_session':session==old['native_session'],'normal_client_login':packets.has(started,'CMSG_PLAYER_LOGIN','from_client'),
        'native_login':packets.has(started,'SMSG_LOGIN_VERIFY_WORLD','from_native'),
        'public_resources':public(state)==old['baseline']['public'],'native_resources':stable(baseline())==old['baseline']['native'],
        'public_visibility':state['appearance']=={'helm':not hidden,'cloak':not hidden},
        'native_visibility':flags(t,oracle)=={'saved_character_flags':expected,'native_player_flags':expected},
        'ui_clean':not state.get('lua_errors') and not state.get('blocked_actions')}
    t.receipt['cases'].append({'id':'character.visibility_reentry.'+('hidden' if hidden else 'restored'),'time':started,
        'before_frame':frame,'after_frame':after,'status':'appearance_session_pass' if all(checks.values()) else 'client_or_protocol_failure',
        'oracle':{'checks':checks}});t.persist()
    if not all(checks.values()):raise RuntimeError('owned full-session visibility/native/public baseline differs')
    return oracle


def run(t,action,path):
    if t.fixture['guid']!=1:raise RuntimeError('requires owned geared primary warrior')
    t.receipt['phase']={'hide-logout':'hidden_logout','restore-logout':'restored_logout','finish':'visibility_session_finished'}[action]
    if action=='hide-logout':
        t.clean_panels();state,frame=t.observe('visibility_session_before')
        session=actors.session_entry(t.fixture)['session'];oracle=Inventory(lab.ROOT,session,1).poll()
        original={'native':stable(baseline()),'public':public(state),'appearance':state['appearance'],'frame':frame}
        if original['appearance']!={'helm':True,'cloak':True} or flags(t,oracle)!={'saved_character_flags':0,'native_player_flags':0}:
            raise RuntimeError('requires original shown helm/cloak and exact zero native visibility flags')
        t.receipt.update(baseline=original,native_session=session);t.persist()
        settings(t,oracle,False,None);logout(t,0xc00,'hidden')
    else:
        old=source(t,path,'hidden_logout' if action=='restore-logout' else 'restored_logout')
        oracle=enter(t,old,action=='restore-logout')
        if action=='restore-logout':
            settings(t,oracle,True,old['search_original']);logout(t,0,'restored')
        else:
            t.clean_panels();t.receipt['original_visibility_restored']=True
    t.receipt.update(native_after=stable(baseline()),native_resources_preserved=stable(baseline())==t.receipt['baseline']['native']);t.persist()
    if not t.receipt['native_resources_preserved']:raise RuntimeError('session trial changed original native resources')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['hide-logout','restore-logout','finish'])
    p.add_argument('--output',type=Path,required=True);p.add_argument('--source',type=Path)
    p.add_argument('--reviewed-character-selection',action='store_true');a=p.parse_args()
    if a.action!='hide-logout' and (not a.source or not a.reviewed_character_selection):p.error('require source and separate selection visual review')
    t=Trial(a.output,controller='code')
    try:run(t,a.action,a.source);close(t,True)
    except Exception as e:
        t.receipt['native_after']=stable(baseline());t.receipt['saved_visibility_after']=saved_flags(t)
        close(t,False,f'{type(e).__name__}: {e}')
