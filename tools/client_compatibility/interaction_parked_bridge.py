"""Keep the existing owned scout offline across a reviewed bridge deployment."""
import argparse,json,time
from pathlib import Path
from . import lab_runtime as lab,owned_input
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_bridge_deploy import shot,identity
from .observation.journal import latest


def native(t):
    if t.fixture['actor']!='scout' or t.fixture['guid']!=2:raise RuntimeError('requires the existing owned scout')
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT * FROM client442_characters.characters WHERE guid=2 AND account=%s',(t.fixture['account_id'],))
        row=q.fetchone()
        if row is None:raise RuntimeError('owned parked scout is absent')
        state=dict(zip([x[0] for x in q.description],row))
    if state['online']!=0 or state['name']!='Harnesstwo' or state['level']!=1:
        raise RuntimeError('owned scout is not parked offline at its original identity')
    return json.loads(json.dumps(state))


def capture(out):
    with actor('scout'):
        t=Trial(out,controller='code')
        try:
            t.receipt.update(parked_native=native(t),parked_frame=shot(t.out/'scout_selection.png'),
                completed=True,custom_script_permission='blocked_by_user',
                qualified_scope='Read-only owned offline scout preflight; no input or gameplay qualification.')
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
        finally:t.receipt['finished_at']=time.time();t.persist()
        if not t.receipt['completed']:raise RuntimeError(t.receipt['failure'])


def review(t,path,old,kind):
    path=path.resolve()
    if not path.is_relative_to(lab.ROOT/'evidence'):raise ValueError('requires owned parked-scout visual review')
    checked=json.loads(path.read_text());frame=checked.get('frame',{});image=path.parent/frame.get('file','')
    monitor=frame.get('monitor',{});current=owned_input.focus()
    if (checked.get('reviewed') is not True or checked.get('kind')!=kind or
        checked.get('selected_character')!='Harnesstwo' or checked.get('selected_level')!=1 or
        checked.get('episode_sha256')!=lab.sha256(old) or
        not image.resolve().is_relative_to(lab.ROOT/'evidence') or not image.is_file() or
        frame.get('sha256')!=lab.sha256(image) or not 0<=time.time()-image.stat().st_mtime<=120 or
        not monitor.get('second_monitor_verified') or monitor.get('pid')!=t.receipt['runtime']['client']['pid'] or
        monitor.get('input_isolation',{}).get('actor')!='scout' or
        monitor.get('input_isolation',{}).get('game_pid')!=current['input_isolation']['game_pid']):
        raise RuntimeError('fresh reviewed parked scout identity or owned monitor differs')
    return checked


def baseline(t,path):
    old=path.parent/'episode.json';previous=json.loads(old.read_text())
    if (previous.get('completed') is not True or not previous.get('finished_at') or
        previous.get('actor')!=t.fixture or previous.get('runtime')!=t.receipt['runtime'] or
        native(t)!=previous.get('parked_native')):
        raise RuntimeError('closed parked scout preflight differs')
    checked=review(t,path,old,'before_bridge_deployment')
    if checked['frame']['sha256']!=previous['parked_frame']['sha256']:
        raise RuntimeError('parked scout preflight image differs')
    t.receipt.update(parked_native=previous['parked_native'],parked_frame=shot(t.out/'scout_parked_before.png'),
        parked_review_source={'file':str(path),'sha256':lab.sha256(path)},completed=True,
        custom_script_permission='blocked_by_user',
        qualified_scope='Offline scout baseline only; deployment must restore selection without world entry.')
    return {'parked':True,'guid':2,'name':'Harnesstwo','level':1}


def finish(out,path):
    report=json.loads((out/'deployment.json').read_text())
    if (not report.get('parked_scout') or identity('worldserver')!=report['native'] or
        identity('modern_world')!=report['after'] or 'scout' in report['reconnected']):
        raise RuntimeError('parked-scout deployment identity differs or already finished')
    old=out/'scout_before/episode.json';previous=json.loads(old.read_text())
    with actor('scout'):
        t=Trial(out/'scout_parked_after',controller='code')
        try:
            if t.receipt['runtime']['client']!=previous['runtime']['client'] or native(t)!=previous['parked_native']:
                raise RuntimeError('parked scout lifetime or native character changed')
            review(t,path,old,'after_bridge_deployment')
            authenticated=latest(lab.ROOT/'logs/modern_world.jsonl',lambda r:r.get('event')=='world_authenticated'
                and r.get('account_id')==t.fixture['account_id'] and r.get('time',0)>=report['started_at'])
            if not authenticated:raise RuntimeError('parked scout has no attributable new realm connection')
            session=authenticated['session']
            enumerated=latest(lab.ROOT/'logs/modern_world.jsonl',lambda r:r.get('session')==session and
                r.get('name')=='SMSG_ENUM_CHARACTERS_RESULT' and r.get('direction')=='to_client')
            entered=latest(lab.ROOT/'logs/modern_world.jsonl',lambda r:r.get('session')==session and
                r.get('event') in ('native_player_created','world_connection_closed','native_stream_closed'))
            if not enumerated or entered:raise RuntimeError('parked scout has entered the world or lost its realm connection')
            t.receipt.update(completed=True,parked_native=native(t),parked_frame=shot(t.out/'scout_parked_restored.png'),
                selection_review_source={'file':str(path),'sha256':lab.sha256(path)},custom_script_permission='blocked_by_user',
                session=session,restoration_checks={'native_unchanged':True,'same_client_lifetime':True,
                'fresh_owned_selection_review':True,'new_realm_enumeration':True,'no_world_entry':True},
                qualified_scope='Parked scout deployment restoration only; no game input or gameplay qualification.')
            report['reconnected']['scout']={'completed':True,'parked':True,'session':session}
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
        finally:t.receipt['finished_at']=time.time();t.persist()
        report.setdefault('parked_reconnect_attempt',{})['scout']={'completed':t.receipt['completed'],
            'failure':t.receipt['failure'],'episode':str(t.out/'episode.json'),'sha256':lab.sha256(t.out/'episode.json')}
        if len(report['reconnected'])==2:
            report.update(finished_at=time.time(),completed=all(r['completed'] for r in report['reconnected'].values()))
        lab.private_write(out/'deployment.json',json.dumps(report,indent=2)+'\n')
        print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
        if not t.receipt['completed']:raise RuntimeError(t.receipt['failure'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['capture','finish'])
    p.add_argument('--output',type=Path,required=True);p.add_argument('--review',type=Path);a=p.parse_args()
    if a.action=='capture':capture(a.output)
    elif a.review:finish(a.output,a.review)
    else:p.error('finish requires the fresh visual review')
