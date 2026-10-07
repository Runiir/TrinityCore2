"""Prepare a native Warlock on the existing scout and preserve its parked origin."""
import argparse,asyncio,json,time
from pathlib import Path
from . import actors,lab_runtime as lab,owned_input
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_bridge_deploy import shot,identity
from .interaction_parked_bridge import native,review as parked_review
from .interaction_character_creator_probe import roster
from .interaction_owned_language_fixture import logout
from .interaction_spellbook_navigation import known
from .interaction_spellbook_professions import skills
from .interaction_spellbook_actions import saved_actions
from .observation.inventory import Inventory
from .interaction_spellbook_recon import resources
from .observation.journal import Cursor,entries


SCRIPT_BOUNDARY={'original':'0','current_stock_disabled':'1','original_restored':False}


def character(guid,account):
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT * FROM client442_characters.characters WHERE guid=%s AND account=%s',(guid,account))
        row=q.fetchone()
        if row is None:raise RuntimeError('owned character is absent')
        return json.loads(json.dumps(dict(zip([x[0] for x in q.description],row))))


def saved(guid):
    quests={}
    with lab.connection() as c,c.cursor() as q:
        for table in ['character_queststatus','character_queststatus_rewarded']:
            q.execute('SELECT * FROM client442_characters.'+table+' WHERE guid=%s ORDER BY quest',(guid,))
            quests[table]=json.loads(json.dumps(q.fetchall()))
    return {'spells':known(guid),'skills':skills(guid),'actions':saved_actions(guid),'quests':quests}


def pets(guid):
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT * FROM client442_characters.character_pet WHERE owner=%s ORDER BY id',(guid,))
        columns=[x[0] for x in q.description]
        return json.loads(json.dumps([dict(zip(columns,row)) for row in q.fetchall()]))


def origin_checks(old):
    origin=old['origin_actor']
    return {'original_character':character(2,origin['account_id'])==old['origin_native'],
        'original_saved_rows':saved(2)==old['origin_saved'],
        'native_worldserver':identity('worldserver')==old['runtime']['worldserver']}


def prepare(t,path,review_path):
    path=path.resolve();old=json.loads(path.read_text())
    if (path.name!='episode.json' or not path.is_relative_to(lab.ROOT/'evidence') or
        old.get('completed') is not True or old.get('failure') is not None or not old.get('finished_at') or
        old.get('actor')!=t.fixture or old.get('runtime')!=t.receipt['runtime'] or
        not old.get('qualified_scope','').startswith('Read-only owned offline scout preflight') or
        native(t)!=old.get('parked_native') or (t.fixture['guid'],t.fixture['race'],t.fixture['class'],t.fixture['level'])!=(2,1,1,1)):
        raise RuntimeError('closed original parked scout source differs')
    checked=parked_review(t,review_path,path,'native_class_fixture')
    if checked['frame']['sha256']!=old['parked_frame']['sha256']:
        raise RuntimeError('reviewed original selection image differs')
    before=roster(t)
    if any(row[1]=='Harnesslock' for row in before):raise RuntimeError('class fixture already exists; inspect its prior preparation')
    t.receipt.update(source={'path':str(path),'sha256':lab.sha256(path)},
        origin_actor=t.fixture,origin_native=old['parked_native'],origin_saved=saved(2),origin_roster=before,
        preparation_review={'path':str(review_path),'sha256':lab.sha256(review_path),'frame':checked['frame']},
        phase='native_class_fixture_creation_started',qualified_scope='Normal native-account data preparation only; '
            'no modern character creation, deletion or spellbook qualification.')
    t.persist()
    fixture=asyncio.run(asyncio.wait_for(actors.create_character('Harnesslock',1,9),45))
    if (fixture['account_id']!=t.fixture['account_id'] or fixture['guid'] in [1,2,3] or
        (fixture['character_name'],fixture['race'],fixture['class'],fixture['level'])!=('Harnesslock',1,9,1)):
        raise RuntimeError('created class fixture identity differs')
    checks=origin_checks(t.receipt)
    checks['only_owned_fixture_added']=roster(t)==before+[[fixture['guid'],'Harnesslock',1,9,0,1,0]]
    t.receipt.update(class_actor=fixture,natural_native=character(fixture['guid'],fixture['account_id']),
        natural_saved=saved(fixture['guid']),checks=checks,phase='await_owned_class_lobby_review',
        frame=shot(t.out/'owned_lobby.png'),requires_next_screen_review=True)
    t.persist()
    if not all(checks.values()):raise RuntimeError('class preparation changed the original parked fixture')
    t.receipt['completed']=True


def prepared(t,path,returning=False):
    path=path.resolve()
    if path.name!='episode.json' or not path.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('requires an owned class preparation receipt')
    old=json.loads(path.read_text());expected=old['origin_actor'] if returning else old['class_actor']
    if (old.get('completed') is not True or old.get('failure') is not None or not old.get('finished_at') or
        old.get('phase')!='await_owned_class_lobby_review' or old['origin_actor']['guid']!=2 or
        expected!=t.fixture or old['runtime']!=t.receipt['runtime'] or not all(origin_checks(old).values())):
        raise RuntimeError('owned class preparation or original parked state differs')
    if old.get('protected_baseline'):
        from .interaction_hunter_fixture import protected
        if not all(protected(old).values()):raise RuntimeError('prepared Hunter protected actors differ')
    t.receipt.update(fixture_source={'path':str(path),'sha256':lab.sha256(path)},origin_checks=origin_checks(old))
    t.persist();return old


def reviewed(t,path,control):
    path=path.resolve()
    if not path.is_relative_to(lab.ROOT/'evidence'):raise ValueError('requires an owned screen review')
    d=json.loads(path.read_text());frame=d.get('frame',{});image=path.parent/frame.get('file','')
    m=frame.get('monitor',{});current=owned_input.focus();point=d.get('point',[])
    if (d.get('reviewed') is not True or d.get('control')!=control or
        d.get('fixture_source_sha256')!=t.receipt['fixture_source']['sha256'] or
        not image.resolve().is_relative_to(lab.ROOT/'evidence') or not image.is_file() or
        frame.get('sha256')!=lab.sha256(image) or not 0<=time.time()-image.stat().st_mtime<=120 or
        not m.get('second_monitor_verified') or m.get('pid')!=t.receipt['runtime']['client']['pid'] or
        m.get('input_isolation',{}).get('actor')!='scout' or
        m.get('input_isolation',{}).get('game_pid')!=current['input_isolation']['game_pid'] or
        len(point)!=2 or any(type(v) is not int for v in point) or
        not (0<=point[0]<1280 and 0<=point[1]<720)):
        raise RuntimeError('fresh reviewed owned class screen differs')
    t.receipt['screen_review']={'path':str(path),'sha256':lab.sha256(path),'frame':frame};t.persist()
    return d


def capture(t,path,returning):
    prepared(t,path,returning);t.receipt.update(frame=shot(t.out/'screen.png'),completed=True,
        qualified_scope='Read-only owned class lobby inspection only.')


def lobby(t,path,review_path,stage,returning):
    old=prepared(t,path,returning)
    control={'dismiss':'Okay','reconnect':'Reconnect','realm':'Client442 Lab','character':t.fixture['character_name']}[stage]
    d=reviewed(t,review_path,control);point=d['point']
    if stage=='character' and not (1040<=point[0]<1280 and 70<=point[1]<560):
        raise RuntimeError('reviewed character row is outside the stock roster')
    if stage=='realm' and d.get('confirm_selected_realm') is not True:
        raise RuntimeError('realm confirmation was not reviewed')
    t.receipt.update(stage=stage,before_frame=shot(t.out/'before.png'));t.persist()
    if stage=='dismiss':t.io.key('Return',hold=1.2)
    else:
        t.io.click(*point,hold=1.2)
        if stage=='realm':time.sleep(1.2);t.io.key('Return',hold=1.2)
    time.sleep(12);checks=origin_checks(old)
    t.receipt.update(frame=shot(t.out/'next_screen.png'),checks=checks,requires_next_screen_review=True)
    if not all(checks.values()):raise RuntimeError('lobby input changed the original parked fixture')
    t.receipt['completed']=True


def entry_identity(fixture):
    if (fixture.get('actor'),fixture.get('race'),fixture.get('account_id'))!=('scout',1,2):return False
    return (fixture.get('character_name'),fixture.get('level'),fixture.get('class'),fixture.get('guid')) in (
        ('Harnesslock',1,9,4),('Harnessctrl',10,9,5),('Harnesshunt',10,3,6))


def enter(t,path,review_path):
    old=prepared(t,path);d=reviewed(t,review_path,'Enter World')
    name,level=t.fixture['character_name'],t.fixture['level']
    if (not entry_identity(t.fixture) or
        (d.get('selected_character'),d.get('selected_level'))!=(name,level) or d.get('point')!=[640,660]):
        raise RuntimeError('class entry requires its reviewed selected character')
    before=character(t.fixture['guid'],t.fixture['account_id'])
    if before['online']!=0:raise RuntimeError('class fixture is already online')
    cursor=Cursor(lab.ROOT/'evidence/world_packets.jsonl')
    for _ in cursor.poll():pass
    started=time.time();t.receipt.update(native_before_entry=before,phase='owned_class_entry_started');t.persist()
    t.io.click(*d['point'],hold=1.2);time.sleep(8)
    state,frame=t.observe('owned_class_entered',seconds=120)
    session=actors.session_entry(t.fixture)['session']
    login=[{k:r[k] for k in ['time','session','name','direction']} for r in cursor.poll()
        if r.get('session')==session and r.get('time',0)>=started and
        r.get('name') in ['CMSG_PLAYER_LOGIN','SMSG_LOGIN_VERIFY_WORLD']]
    oracle=Inventory(lab.ROOT,session,t.fixture['guid']).poll();checks=origin_checks(old)
    checks.update(owned_name=state['player']==name and state['level']==level,solo=state['group']['members']==0,
        no_lua_errors=not state.get('lua_errors'),no_blocked_actions=not state.get('blocked_actions'),
        ordinary_login=any(r['name']=='CMSG_PLAYER_LOGIN' and r['direction']=='from_client' for r in login),
        native_login=any(r['name']=='SMSG_LOGIN_VERIFY_WORLD' and r['direction']=='from_native' for r in login))
    t.receipt.update(checks=checks,native_session=session,login_packets=login,state=state,frame=frame,
        entered_native=character(t.fixture['guid'],t.fixture['account_id']),entered_saved=saved(t.fixture['guid']),
        resources=resources(oracle),qualified_scope='Native class fixture entry and public state inspection only; '
            'no modern creation or remaining spellbook operation qualification.');t.persist()
    if not all(checks.values()):raise RuntimeError('class entry state or original preservation differs')
    t.receipt.update(completed=True,phase='owned_class_entered')


def park(t,path):
    old=prepared(t,path);actors.session_entry(t.fixture);t.clean_panels();logout(t)
    checks=origin_checks(old);checks['class_offline']=character(t.fixture['guid'],t.fixture['account_id'])['online']==0
    if not all(checks.values()):raise RuntimeError('class parking changed the original fixture')
    if actors.register(2)!=old['origin_actor']:raise RuntimeError('original actor registration differs')
    t.receipt.update(checks=checks,phase='await_original_selection_review',frame=shot(t.out/'origin_selection.png'),
        retained_class_fixture=character(t.fixture['guid'],t.fixture['account_id']),
        retained_class_saved=saved(t.fixture['guid']),retained_class_pets=pets(t.fixture['guid']),completed=True,
        qualified_scope='Class fixture parked and original actor registration restored. New owned class fixture retained; '
            'original account roster is intentionally expanded, not restored.')


def settled_park(t,path,failed_path):
    """Finish registration after an interrupted, already completed logout."""
    old=prepared(t,path);failed_path=failed_path.resolve()
    if failed_path.name!='episode.json' or not failed_path.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('requires a closed interrupted owned parking receipt')
    failed=json.loads(failed_path.read_text())
    if (failed.get('completed') is not False or not failed.get('finished_at') or
        failed.get('failure')!='InterruptedError: parking process terminated by SIGTERM (exit 143)' or
        failed.get('actor')!=t.fixture or failed.get('runtime')!=t.receipt['runtime'] or
        failed.get('fixture_source',{}).get('sha256')!=lab.sha256(path)):
        raise RuntimeError('closed interrupted parking source differs')
    session=actors.session_entry(t.fixture)['session']
    packets=[{k:r[k] for k in ('time','session','name','direction')} for r in
        entries(lab.ROOT/'evidence/world_packets.jsonl') if r.get('session')==session and
        failed['started_at']<=r.get('time',0)<=failed['finished_at'] and
        r.get('name') in ('CMSG_LOGOUT_REQUEST','SMSG_LOGOUT_COMPLETE')]
    checks=origin_checks(old)
    checks.update(class_offline=character(t.fixture['guid'],t.fixture['account_id'])['online']==0,
        ordinary_logout=any(r['name']=='CMSG_LOGOUT_REQUEST' and r['direction']=='from_client' for r in packets),
        native_logout=any(r['name']=='SMSG_LOGOUT_COMPLETE' and r['direction']=='from_native' for r in packets),
        delivered_logout=any(r['name']=='SMSG_LOGOUT_COMPLETE' and r['direction']=='to_client' for r in packets))
    if not all(checks.values()):raise RuntimeError('interrupted logout did not complete with original preservation')
    if actors.register(2)!=old['origin_actor']:raise RuntimeError('original actor registration differs')
    t.receipt.update(interrupted_source={'path':str(failed_path),'sha256':lab.sha256(failed_path)},
        logout_packets=packets,checks=checks,phase='await_original_selection_review',
        frame=shot(t.out/'origin_selection.png'),retained_class_fixture=character(t.fixture['guid'],t.fixture['account_id']),
        retained_class_saved=saved(t.fixture['guid']),retained_class_pets=pets(t.fixture['guid']),
        input_sent=False,completed=True,qualified_scope='Observed completed logout after interrupted parking; '
            'original registration restored without replaying input. Interrupted receipt stays excluded.')


def settled_entry(t,path,failed_path):
    old=prepared(t,path);failed_path=failed_path.resolve()
    if failed_path.name!='episode.json' or not failed_path.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('requires a closed owned failed entry')
    failed=json.loads(failed_path.read_text())
    if (failed.get('completed') or failed.get('failure')!='RuntimeError: interaction fixture is unsafe' or
        not failed.get('finished_at') or failed.get('phase')!='owned_class_entry_started' or
        failed.get('actor')!=t.fixture or failed.get('runtime')!=t.receipt['runtime'] or
        failed.get('fixture_source',{}).get('sha256')!=lab.sha256(path) or
        not entry_identity(t.fixture) or t.fixture['level']!=10 or
        character(t.fixture['guid'],t.fixture['account_id'])['online']!=1):
        raise RuntimeError('failed eligible entry differs; never replay login input')
    session=actors.session_entry(t.fixture)['session']
    login=[{k:r[k] for k in ['time','session','name','direction']} for r in entries(lab.ROOT/'evidence/world_packets.jsonl')
        if r.get('session')==session and failed['started_at']<=r.get('time',0)<=failed['finished_at'] and
        r.get('name') in ['CMSG_PLAYER_LOGIN','SMSG_LOGIN_VERIFY_WORLD']]
    state,frame=t.observe('entry_settled')
    oracle=Inventory(lab.ROOT,session,t.fixture['guid']).poll();checks=origin_checks(old)
    checks.update(owned_name=state['player']==t.fixture['character_name'] and state['level']==10,solo=state['group']['members']==0,
        no_lua_errors=not state.get('lua_errors'),no_blocked_actions=not state.get('blocked_actions'),
        ordinary_login=any(r['name']=='CMSG_PLAYER_LOGIN' and r['direction']=='from_client' for r in login),
        native_login=any(r['name']=='SMSG_LOGIN_VERIFY_WORLD' and r['direction']=='from_native' for r in login))
    t.receipt.update(failed_entry_source={'path':str(failed_path),'sha256':lab.sha256(failed_path)},
        checks=checks,native_session=session,login_packets=login,state=state,frame=frame,
        entered_native=character(t.fixture['guid'],t.fixture['account_id']),entered_saved=saved(t.fixture['guid']),
        resources=resources(oracle),input_sent=False,phase='owned_class_entered',
        qualified_scope='Read-only settling of the actual earlier ordinary entry; failed whole entry stays excluded. '
            'No extra login, health grant or gameplay qualification.')
    if not all(checks.values()):raise RuntimeError('settled entry or original preservation differs')
    t.receipt['completed']=True


def finish(t,path,review_path):
    old=prepared(t,path,True);d=reviewed(t,review_path,'Harnesstwo')
    if (d.get('selected_character'),d.get('selected_level'))!=('Harnesstwo',1):
        raise RuntimeError('requires the reviewed original selection')
    checks=origin_checks(old);checks['origin_registration']=actors.load()==old['origin_actor']
    checks['class_offline']=character(old['class_actor']['guid'],old['class_actor']['account_id'])['online']==0
    t.receipt.update(checks=checks,frame=shot(t.out/'original_restored.png'),completed=all(checks.values()),
        qualified_scope='Original parked character, saved rows and selected identity restored; class fixture retained.')
    if not all(checks.values()):raise RuntimeError('original parked restoration differs')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','capture','lobby','enter','settle-enter','park','settle-park','finish'])
    p.add_argument('--source',type=Path,required=True);p.add_argument('--review',type=Path)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--returning',action='store_true')
    p.add_argument('--failed-source',type=Path)
    p.add_argument('--stage',choices=['dismiss','reconnect','realm','character']);a=p.parse_args()
    if a.action in ['prepare','lobby','enter','finish'] and not a.review:p.error('requires a fresh owned visual review')
    if a.action=='lobby' and not a.stage:p.error('requires one reviewed lobby stage')
    if a.action in ['settle-enter','settle-park'] and not a.failed_source:p.error('requires the closed failed source')
    with actor('scout'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2,chat_open_retry=True)
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:
            if a.action=='prepare':prepare(t,a.source,a.review)
            elif a.action=='capture':capture(t,a.source,a.returning)
            elif a.action=='lobby':lobby(t,a.source,a.review,a.stage,a.returning)
            elif a.action=='enter':enter(t,a.source,a.review)
            elif a.action=='settle-enter':settled_entry(t,a.source,a.failed_source)
            elif a.action=='park':park(t,a.source)
            elif a.action=='settle-park':settled_park(t,a.source,a.failed_source)
            else:finish(t,a.source,a.review)
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ['phase','completed','failure']}),flush=True)
