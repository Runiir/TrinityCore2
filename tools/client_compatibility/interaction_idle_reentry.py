"""Reenter the owned scout from its separately reviewed character-selection screen."""
import argparse,json,time
from pathlib import Path
from . import lab_runtime as lab,actors
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_bridge_deploy import shot
from .interaction_lifecycle import Packets
from .interaction_spellbook_navigation import known
from .observation.journal import entries
from .observation.journal import Cursor


def run(t,source):
    source=source.resolve()
    if source.name!='episode.json' or not source.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('require the private failed scout observer preflight')
    old=json.loads(source.read_text())
    if (old['actor']!=t.fixture or old['runtime']!=t.receipt['runtime'] or old['completed'] or
        old.get('native_pose_before') or not old.get('finished_at') or
        old['failure']!='RuntimeError: UI observation did not become decodable' or
        t.fixture['guid']!=2):raise RuntimeError('exact scout preflight source differs')
    reviewed=source.parent/'cleanup_latest.png';frame=shot(t.out/'selection_before.png')
    t.receipt.update(source={'file':str(source),'sha256':lab.sha256(source)},selection_frame=frame,
        reviewed_selection={'file':str(reviewed),'sha256':lab.sha256(reviewed),'character':'Harnesstwo',
        'level':1,'input':[640,661],'reviewed_character_selection':True});t.persist()
    prior=actors.session_entry(t.fixture)['session'];packets=Packets(prior);started=time.time()
    t.execute({'kind':'click','value':[640,661]});time.sleep(8)
    state,frame=t.observe('scout_reentered',seconds=120);entry=actors.session_entry(t.fixture)
    checks={'owned_guid':state['guid']==t.guid,
        'name':state['player']=='Harnesstwo','level':state['level']==1,'money':state['money']==0,
        'starter_mainhand':state['equipment'][15]==49778,'persisted_spells':known(2)==[],
        'solo':state['group']['members']==0,'no_lua_errors':not state.get('lua_errors'),
        'no_blocked_actions':not state.get('blocked_actions'),
        'ordinary_login':packets.has(started,'CMSG_PLAYER_LOGIN','from_client'),
        'native_login':packets.has(started,'SMSG_LOGIN_VERIFY_WORLD','from_native')}
    t.receipt.update(previous_session=prior,session=entry['session'],reentry_checks=checks,frame=frame);t.persist()
    if not all(checks.values()):raise RuntimeError('scout reentry fixture checks differ')


def verify_completed_input(t,source):
    source=source.resolve()
    if source.name!='episode.json' or not source.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('require the private failed packet-reader reentry')
    old=json.loads(source.read_text());failed={k for k,v in old.get('reentry_checks',{}).items() if not v}
    if (old['actor']!=t.fixture or old['runtime']!=t.receipt['runtime'] or old['completed'] or
        not old.get('finished_at') or old['failure']!='RuntimeError: scout reentry fixture checks differ' or
        failed!={'ordinary_login','native_login'}):raise RuntimeError('exact reader failure differs')
    state,frame=t.observe('verified_scout_reentry');session=actors.session_entry(t.fixture)['session']
    checks={'same_session':session==old['session'],'owned_guid':state['guid']==t.guid,
        'name':state['player']=='Harnesstwo','level':state['level']==1,'money':state['money']==0,
        'starter_mainhand':state['equipment'][15]==49778,'persisted_spells':known(2)==[],
        'solo':state['group']['members']==0,'no_lua_errors':not state.get('lua_errors'),
        'no_blocked_actions':not state.get('blocked_actions')}
    names={'CMSG_PLAYER_LOGIN','SMSG_LOGIN_VERIFY_WORLD'}
    packets=[{k:r[k] for k in ['time','name','direction']} for r in entries(lab.ROOT/'evidence/world_packets.jsonl')
        if r.get('session')==session and r.get('time',0)>=old['started_at'] and r.get('name') in names]
    checks['ordinary_login']=any(r['name']=='CMSG_PLAYER_LOGIN' and r['direction']=='from_client' for r in packets)
    checks['native_login']=any(r['name']=='SMSG_LOGIN_VERIFY_WORLD' and r['direction']=='from_native' for r in packets)
    t.receipt.update(source={'file':str(source),'sha256':lab.sha256(source)},checks=checks,packets=packets,
        frame=frame,scope='Read-only verification of an already completed owned reentry; no replayed login input.');t.persist()
    if not all(checks.values()):raise RuntimeError('completed reentry verification differs')


def run_completed_baseline(t,source,selection):
    source=source.resolve();selection=selection.resolve()
    if source.name!='episode.json' or not source.is_relative_to(lab.ROOT/'evidence') or \
        selection.suffix!='.png' or not selection.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('require an owned completed scout baseline and reviewed selection frame')
    old=json.loads(source.read_text());state=old.get('observation',{}).get('state',{})
    frame=json.loads(selection.with_suffix('.json').read_text())['frame']
    monitor=frame['monitor']
    if (not old.get('completed') or not old.get('finished_at') or old['actor']!=t.fixture or
        old['runtime']!=t.receipt['runtime'] or t.fixture['guid']!=2 or state.get('guid')!=t.guid or
        state.get('player')!='Harnesstwo' or state.get('money')!=0 or state.get('equipment',[0]*19)[15]!=49778 or
        frame['sha256']!=lab.sha256(selection) or monitor.get('second_monitor_verified') is not True or
        monitor['input_isolation']['actor']!='scout' or monitor['pid']!=t.receipt['runtime']['client']['pid'] or
        not 0<=time.time()-selection.stat().st_mtime<=120):
        raise RuntimeError('completed scout baseline, owned monitor or fresh reviewed screen differs')
    original=old['native_pose_before'];cursor=Cursor(lab.ROOT/'evidence/world_packets.jsonl')
    for packet in cursor.poll():pass
    t.receipt.update(source={'file':str(source),'sha256':lab.sha256(source)},
        reviewed_selection={'frame':frame,'character':'Harnesstwo','input':[640,661],
            'reviewed_character_selection':True});t.persist()
    started=time.time();t.execute({'kind':'click','value':[640,661]});time.sleep(8)
    state,frame=t.observe('scout_reentered',seconds=120);session=actors.session_entry(t.fixture)['session']
    packets=[{k:p[k] for k in ['time','name','direction']} for p in cursor.poll() if
        p.get('session')==session and p.get('time',0)>=started and p.get('name') in
        {'CMSG_PLAYER_LOGIN','SMSG_LOGIN_VERIFY_WORLD'}]
    checks={'owned_guid':state['guid']==t.guid,'name':state['player']=='Harnesstwo','level':state['level']==1,
        'money':state['money']==0,'starter_mainhand':state['equipment'][15]==49778,'persisted_spells':known(2)==[],
        'solo':state['group']['members']==0,'no_lua_errors':not state.get('lua_errors'),
        'no_blocked_actions':not state.get('blocked_actions'),
        'ordinary_login':any(p['name']=='CMSG_PLAYER_LOGIN' and p['direction']=='from_client' for p in packets),
        'native_login':any(p['name']=='SMSG_LOGIN_VERIFY_WORLD' and p['direction']=='from_native' for p in packets)}
    t.receipt.update(session=session,reentry_checks=checks,packets=packets,frame=frame);t.persist()
    if not all(checks.values()):raise RuntimeError('completed-baseline scout reentry differs')
    from .observation.inventory import Inventory
    from .interaction_sit_stand import pose,afk
    from .interaction_actionbar_pages import detail
    from .interaction_trial import binding_key
    native=Inventory(lab.ROOT,session,2).poll()
    if afk(native)!=original['afk']:t.execute({'kind':'chat','value':'/afk'})
    if pose(native)['stand']!=original['pose']['stand']:
        if {pose(native)['stand'],original['pose']['stand']}!={0,1}:raise RuntimeError('unsupported reentry pose')
        bar=detail(t,'scout_reentry_pose_binding');t.execute({'kind':'key','value':binding_key(bar['keys']['SITORSTAND'][0]),'hold':.4})
        time.sleep(12)
    t.receipt['original_pose_afk_restored']=pose(native)==original['pose'] and afk(native)==original['afk'];t.persist()
    if not t.receipt['original_pose_afk_restored']:raise RuntimeError('original scout pose/AFK differs')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--reviewed-character-selection',action='store_true')
    p.add_argument('--verify-completed-input',action='store_true')
    p.add_argument('--completed-baseline',action='store_true');p.add_argument('--selection-frame',type=Path);a=p.parse_args()
    if a.completed_baseline and (a.verify_completed_input or not a.selection_frame):
        p.error('completed-baseline reentry requires its fresh reviewed selection frame')
    if not a.verify_completed_input and not a.reviewed_character_selection:
        p.error('review the owned selected Harnesstwo screen before reentry')
    with actor('scout'):
        t=Trial(a.output,controller='code')
        try:
            if a.completed_baseline:run_completed_baseline(t,a.source,a.selection_frame)
            else:(verify_completed_input if a.verify_completed_input else run)(t,a.source)
            t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
