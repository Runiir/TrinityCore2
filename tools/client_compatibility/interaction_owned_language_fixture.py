"""Use a native dwarf on the existing scout client, then restore Harnesstwo."""
import argparse,asyncio,json,time
from pathlib import Path
from . import actors,lab_runtime as lab,owned_input
from .interaction_social import actor
from .interaction_trial import Trial,binding_key
from .interaction_bridge_deploy import shot,identity
from .interaction_lifecycle import Packets
from .interaction_chat_window import detail
from .interaction_chat_settings import signature
from .interaction_spellbook_navigation import known
from .interaction_spellbook_professions import skills
from .interaction_spellbook_actions import saved_actions
from .interaction_spellbook_recon import resources
from .interaction_stance_bar import native_state,restored_native_state
from .interaction_sit_stand import pose,afk
from .interaction_ground_movement import position
from .interaction_actionbar_pages import detail as bar_detail
from .observation.inventory import Inventory
from .observation.journal import Cursor


def baseline(t,oracle):
    state,frame=t.observe('original_owned_character')
    return {'state':state,'frame':frame,'resources':resources(oracle),'stats':native_state(oracle),
        'spells':known(t.fixture['guid']),'skills':skills(t.fixture['guid']),'actions':saved_actions(t.fixture['guid']),
        'pose':pose(oracle),'afk':afk(oracle),'position':position(t.fixture['guid']),
        'target':oracle.pair(t.fixture['guid'],'UNIT_FIELD_TARGET'),'chat':detail(t,'original_owned_chat')}


def logout(t):
    session=actors.session_entry(t.fixture)['session'];packets=Packets(session);started=time.time()
    t.submit_chat('/logout');deadline=time.monotonic()+45
    while not packets.has(started,'SMSG_LOGOUT_COMPLETE','from_native'):
        if time.monotonic()>deadline:raise RuntimeError('ordinary owned logout did not complete')
        time.sleep(.2)
    if not packets.has(started,'CMSG_LOGOUT_REQUEST','from_client'):
        raise RuntimeError('ordinary owned logout request is absent')
    with lab.connection() as con,con.cursor() as q:
        q.execute('SELECT online FROM client442_characters.characters WHERE guid=%s AND account=%s',
            (t.fixture['guid'],t.fixture['account_id']))
        if q.fetchone()!=(0,):raise RuntimeError('owned character did not become offline')


def prepare(t):
    if t.fixture['guid']!=2 or t.fixture['race']!=1 or t.fixture['class']!=1 or t.fixture['level']!=1:
        raise RuntimeError('requires the original owned Harnesstwo fixture')
    t.clean_panels();session=actors.session_entry(t.fixture)['session'];oracle=Inventory(lab.ROOT,session,2).poll()
    original=baseline(t,oracle)
    if original['state']['group']['members'] or original['target'] not in [0,1,2] or original['spells']:
        raise RuntimeError('original scout fixture differs from the frozen solo baseline')
    t.receipt.update(origin_actor=t.fixture,origin_baseline=original,native_world=identity('worldserver'),
        phase='owned_origin_logout_started');t.persist();logout(t)
    # Normal owned native-account character creation prepares data only. It
    # does not qualify the modern character-creation UI. No extra game client.
    fixture=asyncio.run(asyncio.wait_for(actors.create_character('Harnessdwarf',3,1),45))
    if (fixture['account_id']!=t.fixture['account_id'] or fixture['guid']==2 or
        (fixture['race'],fixture['class'],fixture['level'])!=(3,1,1)):
        raise RuntimeError('created language actor ownership or native identity differs')
    t.receipt.update(language_actor=fixture,natural_rows={'spells':known(fixture['guid']),'skills':skills(fixture['guid'])},
        phase='await_owned_dwarf_lobby_review',frame=shot(t.out/'owned_lobby.png'),completed=True)


def prepared(t,path,returning=False):
    path=path.resolve()
    if path.name!='episode.json' or not path.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('requires a private owned fixture receipt')
    d=json.loads(path.read_text())
    expected=d['origin_actor'] if returning else d['language_actor']
    if (not d['completed'] or not d.get('finished_at') or d['phase']!='await_owned_dwarf_lobby_review' or
        d['origin_actor']['guid']!=2 or t.fixture!=expected or d['runtime']!=t.receipt['runtime'] or
        identity('worldserver')!=d['native_world']):
        raise RuntimeError('owned fixture or process lifetime differs')
    t.receipt['fixture_source']={'path':str(path),'sha256':lab.sha256(path)};t.persist()
    return d


def reviewed(t,path):
    d=json.loads(path.read_text());f=d['frame'];image=path.parent/f['file'];m=f['monitor']
    current=owned_input.focus()
    if (not image.resolve().is_relative_to(lab.ROOT/'evidence') or
        d.get('fixture_source_sha256')!=t.receipt['fixture_source']['sha256'] or
        lab.sha256(image)!=f['sha256'] or not m['second_monitor_verified'] or
        m['input_isolation']['actor']!='scout' or m['pid']!=lab.owned_process('client')['pid'] or
        m['input_isolation']['game_pid']!=current['input_isolation']['game_pid']):
        raise RuntimeError('reviewed owned lobby frame differs')
    t.receipt['reviewed_lobby']={'path':str(path),'sha256':lab.sha256(path),'frame':f};t.persist()


def lobby(t,path,review_path,stage,point,returning):
    prepared(t,path,returning);reviewed(t,review_path)
    t.receipt['before_frame']=shot(t.out/'before.png');t.persist()
    if stage=='dismiss':t.io.key('Return',hold=1.2)
    elif stage=='reconnect':t.io.click(640,418,hold=1.2)
    elif stage=='realm':
        t.io.click(465,182,hold=1.2);time.sleep(1.2);t.io.key('Return',hold=1.2)
    elif stage=='character':
        if point is None or not 1040<=point[0]<1280 or not 70<=point[1]<560:
            raise ValueError('requires the actual reviewed owned character-row point')
        t.io.click(*point,hold=1.2)
    else:raise ValueError('unsupported reviewed lobby stage')
    time.sleep(12);t.receipt.update(stage=stage,frame=shot(t.out/'next_screen.png'),completed=True,
        requires_next_screen_review=True)


def enter(t,path,review_path,returning,return_source):
    old=prepared(t,path,returning);reviewed(t,review_path)
    if returning:
        back=json.loads(return_source.read_text())
        if (not back['completed'] or back.get('phase')!='await_owned_origin_selection' or
            back['fixture_source']['sha256']!=lab.sha256(path) or back['runtime']!=t.receipt['runtime']):
            raise RuntimeError('owned return source differs')
    cursor=Cursor(lab.ROOT/'evidence/world_packets.jsonl')
    for _ in cursor.poll():pass
    started=time.time();t.io.key('Return',hold=1.2);time.sleep(8)
    state,frame=t.observe('owned_character_entered',seconds=240)
    session=actors.session_entry(t.fixture)['session'];oracle=Inventory(lab.ROOT,session,t.fixture['guid']).poll()
    checks={'owned_name':state['player']==t.fixture['character_name'],'solo':state['group']['members']==0,
        'no_lua_errors':not state.get('lua_errors'),'no_blocked_actions':not state.get('blocked_actions'),
        'native_world_unchanged':identity('worldserver')==old['native_world']}
    if returning:
        base=old['origin_baseline']
        if pose(oracle)!=base['pose']:
            if {pose(oracle)['stand'],base['pose']['stand']}!={0,1}:raise RuntimeError('unsupported original pose')
            bar=bar_detail(t,'restore_origin_pose');t.execute({'kind':'key','value':binding_key(bar['keys']['SITORSTAND'][0]),'hold':1.2});time.sleep(12)
        if afk(oracle)!=base['afk']:t.execute({'kind':'chat','value':'/afk'})
        public=detail(t,'restored_origin_chat');state,frame=t.observe('owned_origin_restored')
        checks.update(resources=resources(oracle)==base['resources'],stats=restored_native_state(base['stats'],native_state(oracle)),
            spells=known(2)==base['spells'],skills=skills(2)==base['skills'],actions=saved_actions(2)==base['actions'],
            pose=pose(oracle)==base['pose'],afk=afk(oracle)==base['afk'],position=position(2)==base['position'],
            target=oracle.pair(2,'UNIT_FIELD_TARGET')==base['target'],group=state['group']==base['state']['group'],
            raid_profile=state['raid_profile']==base['state']['raid_profile'],languages=public['languages']==base['chat']['languages'],
            chat_settings=signature(public)==signature(base['chat']),channels=public['channels']==base['chat']['channels'])
    else:
        public=detail(t,'natural_language_capability');t.receipt['natural_capability']=public['languages']
        checks.update(native_racial_skill=[111,300,300] in skills(t.fixture['guid']))
    login=[{k:r[k] for k in ['time','session','name','direction']} for r in cursor.poll()
        if r.get('session')==session and r.get('time',0)>=started and r.get('name') in ['CMSG_PLAYER_LOGIN','SMSG_LOGIN_VERIFY_WORLD']]
    checks.update(ordinary_login=any(r['name']=='CMSG_PLAYER_LOGIN' and r['direction']=='from_client' for r in login),
        native_login=any(r['name']=='SMSG_LOGIN_VERIFY_WORLD' and r['direction']=='from_native' for r in login))
    t.receipt.update(checks=checks,login_packets=login,session=session,public=public,frame=frame);t.persist()
    if not all(checks.values()):raise RuntimeError('owned character entry checks differ')
    t.receipt['completed']=True


def return_origin(t,path,language_path):
    old=prepared(t,path);done=json.loads(language_path.read_text());checks=done.get('native_restoration',{}).get('checks',{})
    if (not done.get('finished_at') or done['actor']!=t.fixture or done['runtime']!=t.receipt['runtime'] or
        len(checks)!=10 or not all(checks.values())):
        raise RuntimeError('natural language episode has not restored all native state')
    t.receipt['language_source']={'path':str(language_path),'sha256':lab.sha256(language_path)};t.persist()
    t.clean_panels();logout(t)
    if actors.register(2)!=old['origin_actor']:raise RuntimeError('original owned actor registration differs')
    t.receipt.update(phase='await_owned_origin_selection',frame=shot(t.out/'origin_selection.png'),completed=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','lobby','enter','return'])
    p.add_argument('--output',type=Path,required=True);p.add_argument('--source',type=Path)
    p.add_argument('--review',type=Path);p.add_argument('--reviewed-owned-lobby',action='store_true')
    p.add_argument('--stage',choices=['dismiss','reconnect','realm','character']);p.add_argument('--point',type=int,nargs=2)
    p.add_argument('--returning',action='store_true');p.add_argument('--return-source',type=Path);p.add_argument('--language-source',type=Path)
    a=p.parse_args()
    if a.action!='prepare' and not a.source:p.error('requires the owned preparation source')
    if a.action in ['lobby','enter'] and (not a.review or not a.reviewed_owned_lobby):p.error('requires actual owned lobby review')
    if a.action=='return' and not a.language_source:p.error('requires the closed natural language episode')
    if a.action=='enter' and a.returning and not a.return_source:p.error('requires the completed origin return receipt')
    with actor('scout'):
        t=Trial(a.output,controller='code')
        try:
            if a.action=='prepare':prepare(t)
            elif a.action=='lobby':lobby(t,a.source,a.review,a.stage,a.point,a.returning)
            elif a.action=='enter':enter(t,a.source,a.review,a.returning,a.return_source)
            else:return_origin(t,a.source,a.language_source)
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:
            t.receipt['finished_at']=time.time();t.persist()
            print(json.dumps({k:t.receipt.get(k) for k in ['phase','completed','failure','natural_capability']}),flush=True)
