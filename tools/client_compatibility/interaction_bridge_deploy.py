"""Restart only the owned bridge, then reconnect reviewed lobby screens on HDMI-1."""
import argparse
import fcntl
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import shutil
import time
from . import actors,lab_runtime as lab,owned_input
from .interaction_social import actor
from .interaction_trial import Trial
from .world import control
from . import interaction_bridge_restoration as native_restoration


def identity(kind):
    process=lab.owned_process(kind)
    if not process: raise RuntimeError('owned '+kind+' is absent')
    return {key:process[key] for key in ['pid','start_ticks','engine','build'] if key in process}


def shot(path):
    from tools.second_client import ctl
    ctl._launcher_env=lab.client_environment
    with owned_input.lease():
        monitor=owned_input.focus()
        with redirect_stdout(StringIO()): ctl.shot(str(path))
    return {'file':path.name,'sha256':lab.sha256(path),'monitor':monitor}


def restart(out,version,unavailable_primary_source=None,unavailable_scout_source=None,unavailable_deployment_source=None,combat_source=None):
    out.mkdir(exist_ok=False,parents=True,mode=0o700)
    native=identity('worldserver'); before=identity('modern_world'); control.native_command()
    baselines={};native_baselines={}
    for name in ['primary','scout']:
        with actor(name):
            t=Trial(out/(name+'_before'),controller='code')
            try:
                if name=='primary' and combat_source:
                    from .interaction_character_combat_recovery import unavailable
                    baselines[name]=unavailable(t,combat_source,native,before)
                elif unavailable_deployment_source:
                    from .interaction_deployment_baseline import unavailable_deployment
                    baselines[name]=unavailable_deployment(t,unavailable_deployment_source,native,before)
                elif name=='primary' and unavailable_primary_source:
                    from .interaction_deployment_baseline import unavailable_primary
                    baselines[name]=unavailable_primary(t,unavailable_primary_source,native,before)
                elif name=='scout' and unavailable_scout_source:
                    if not unavailable_primary_source:raise ValueError('scout recovery requires the shared inventory source')
                    from .interaction_deployment_baseline import unavailable_scout
                    baselines[name]=unavailable_scout(t,unavailable_scout_source,unavailable_primary_source,native,before)
                else:
                    actors.session_entry(t.fixture);t.clean_panels();state,frame=t.observe('before_deploy')
                    baselines[name]={key:state.get(key) for key in ['guid','money','equipment','group','raid_profile']}
                    native_baselines[name]=native_restoration.capture(t)
                    t.receipt['bridge_native_baseline']=native_baselines[name]
                    t.receipt['baseline']={'state':state,'frame':frame};t.receipt['completed']=True
                shutil.copytree(lab.REPO/'tools/client_compatibility/observation/addon/ClientMovementHarness',
                    lab.client_root()/'client/_whitemane-60895_/Interface/AddOns/ClientMovementHarness',dirs_exist_ok=True)
            except Exception as error:
                t.receipt['failure']=f'{type(error).__name__}: {error}';raise
            finally: t.receipt['finished_at']=time.time();t.persist()
    report={'schema':'client442_bridge_deployment_v1','started_at':time.time(),'native':native,'before':before,
            'observer_version':version,'baselines':baselines,'reconnected':{}}
    if unavailable_primary_source:report['primary_public_precheck_deferred']=True
    if combat_source:report.update(primary_public_precheck_deferred=True,combat_source=str(combat_source))
    if unavailable_scout_source:report['scout_public_precheck_deferred']=True
    if unavailable_deployment_source:
        report.update(primary_public_precheck_deferred=True,scout_public_precheck_deferred=True,
            unavailable_deployment_source=str(unavailable_deployment_source))
    report['native_baselines']=native_baselines
    lab.private_write(out/'deployment.json',json.dumps(report,indent=2)+'\n')
    lab.stop('modern_world');control.start();report['after']=identity('modern_world')
    if identity('worldserver')!=native: raise RuntimeError('native worldserver changed during bridge deployment')
    report['native_unchanged']=True
    report['read_only_disconnect_settling_seconds']=12
    time.sleep(12)
    for name in ['primary','scout']:
        with actor(name): report.setdefault('lobby_frames',{})[name]=shot(out/(name+'_disconnected.png'))
    lab.private_write(out/'deployment.json',json.dumps(report,indent=2)+'\n')
    print(json.dumps({'native_unchanged':True,'lobby_frames':report['lobby_frames']}),flush=True)


def reconnect(out,name,keyboard_modal=False,character_selection=False,realm_selection=False):
    if not character_selection or realm_selection:
        raise ValueError('Review character selection first; select-realm performs only the reviewed realm inputs. Refusing timed login/cancel/world-entry guesses.')
    report=json.loads((out/'deployment.json').read_text())
    if identity('worldserver')!=report['native'] or identity('modern_world')!=report['after']:
        raise RuntimeError('deployment process identity changed')
    if name in report['reconnected']:raise RuntimeError('actor already reconnected in this deployment')
    # These are the ordinary lobby controls from the separately captured and
    # visually reviewed 1280x720 client screens. Stop on any observation failure.
    inputs=[('okay',[640,380],.4),('reconnect',[640,418],3),('realm',[465,182],.4),
            ('realm_okay',[750,570],3),('enter',[640,661],10)]
    if character_selection and realm_selection:raise ValueError('choose one reviewed lobby screen')
    if character_selection:inputs=inputs[-1:]
    elif realm_selection:inputs=inputs[2:]
    with actor(name):
        t=Trial(out/(name+'_after'),controller='code')
        try:
            t.receipt['lobby_inputs']=[]
            for label,point,delay in inputs:
                frame=shot(t.out/(label+'_before.png'))
                use_key=keyboard_modal and label in ['okay','realm_okay','enter']
                if use_key:t.io.key('Return',hold=.4)
                else:t.io.click(*point)
                time.sleep(delay)
                t.receipt['lobby_inputs'].append({'source':'code_fixture_reconnect','label':label,
                    'point':None if use_key else point,'key':'Return' if use_key else None,'before_frame':frame})
                t.persist()
            # Two background clients can spend longer loading after a long idle.
            # Extend only this read-only readiness wait, never replay login input.
            t.receipt['reentry_observation_timeout']=120;t.persist()
            state,frame=t.observe('reconnected',seconds=120);entry=actors.session_entry(t.fixture)
            restored=all(state.get(key)==value for key,value in report['baselines'][name].items())
            if (state.get('observer_version')!=report['observer_version'] or state.get('lua_errors') or
                    state.get('blocked_actions') or not restored):
                raise RuntimeError('reconnected observer, resources, equipment or group baseline differs')
            t.clean_panels()
            if name in report.get('native_baselines',{}):
                native_restoration.restore(t,report['native_baselines'][name])
                state,frame=t.observe('reconnected_restored')
            t.receipt.update(completed=True,observation={'state':state,'frame':frame,'session':entry['session']})
            report['reconnected'][name]={'session':entry['session'],'completed':True,'frame':frame}
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:
            t.receipt['finished_at']=time.time();t.persist()
            # Independent private-display clients can reconnect concurrently.
            # Merge their results under a short metadata lock instead of losing
            # the other actor's result through last-writer-wins replacement.
            with (out/'deployment.lock').open('a') as handle:
                fcntl.flock(handle,fcntl.LOCK_EX)
                latest=json.loads((out/'deployment.json').read_text())
                latest['reconnected'].update(report['reconnected'])
                latest.setdefault('reconnect_attempts',{})[name]={'completed':t.receipt['completed'],
                    'failure':t.receipt['failure'],'episode':str(t.out/'episode.json'),
                    'sha256':lab.sha256(t.out/'episode.json')}
                expected=1 if latest.get('recovery_source') else 2
                if len(latest['reconnect_attempts'])==expected:
                    latest.update(finished_at=time.time(),completed=all(r['completed'] for r in latest['reconnect_attempts'].values()))
                lab.private_write(out/'deployment.json',json.dumps(latest,indent=2)+'\n')
            print(json.dumps({'actor':name,'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
        if not t.receipt['completed']:raise RuntimeError(t.receipt['failure'])


def resume_login(out,name,attempt=1,dismiss_dialog=False,after_dismiss=False,keyboard_modal=False):
    """Emit one reviewed lobby input, then require a new screen review."""
    report=json.loads((out/'deployment.json').read_text())
    if identity('worldserver')!=report['native'] or identity('modern_world')!=report['after']:
        raise RuntimeError('login resumption requires the same deployment processes')
    with actor(name):
        previous=json.loads((out/(name+'_before')/'episode.json').read_text())
        lifetime=lambda row:{key:row[key] for key in ['pid','start_ticks']}
        if lifetime(identity('client'))!=lifetime(previous['runtime']['client']):
            raise RuntimeError('owned client lifetime differs from the reviewed disconnect screen')
        if attempt not in [1,2]:raise ValueError('bounded login attempts are1 or2')
        prior=out/(name+'_login')/'episode.json'
        if attempt==2 and (not prior.is_file() or not json.loads(prior.read_text()).get('finished_at')):
            raise RuntimeError('second reviewed input requires the closed first input receipt')
        if dismiss_dialog and after_dismiss:raise ValueError('choose one reviewed lobby stage')
        dismissed=out/(name+'_disconnect_dismiss')/'episode.json'
        if after_dismiss and (not dismissed.is_file() or not json.loads(dismissed.read_text()).get('completed')):
            raise RuntimeError('reconnect after modal requires its closed dismissal receipt')
        suffix=('_disconnect_dismiss' if dismiss_dialog else '_login_after_dismiss' if after_dismiss else
            '_login'+('' if attempt==1 else str(attempt)))
        if keyboard_modal:
            if not dismiss_dialog:raise ValueError('keyboard modal input requires the reviewed Okay dialog')
            suffix+='_key'
        t=Trial(out/(name+suffix),controller='code')
        try:
            t.receipt['qualified_scope']='Reviewed disconnect '+('Okay' if dismiss_dialog else 'Reconnect')+' input only; next lobby screen requires separate visual review'
            frame=shot(t.out/'before.png');action={'kind':'click','value':[640,380 if dismiss_dialog else 418],'hold':.4}
            if keyboard_modal:action={'kind':'key','value':'Return','hold':.4}
            if after_dismiss:t.receipt['modal_dismissal']={'file':str(dismissed),'sha256':lab.sha256(dismissed)}
            if attempt==2:
                t.receipt['previous_input']={'file':str(prior),'sha256':lab.sha256(prior),
                    'reason':'Separately reviewed unchanged disconnect dialog; first acknowledged short click did not advance.'}
            t.receipt['lobby_input']={'input':action,'before_frame':frame};t.persist()
            if action['kind']=='key':t.io.key(action['value'],hold=action['hold'])
            else:t.io.click(*action['value'],hold=action['hold'])
            t.receipt['read_only_lobby_settling_seconds']=12;t.persist();time.sleep(12)
            t.receipt.update(completed=True,next_screen=shot(t.out/'next_screen.png'),requires_lobby_review=True)
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({'actor':name,'input_completed':t.receipt['completed'],'failure':t.receipt['failure'],
            'requires_separate_lobby_review':True}),flush=True)
        if not t.receipt['completed']:raise RuntimeError(t.receipt['failure'])


def select_realm(out,name):
    """Emit only realm selection inputs, then retain the next screen for review."""
    report=json.loads((out/'deployment.json').read_text())
    if identity('worldserver')!=report['native'] or identity('modern_world')!=report['after']:
        raise RuntimeError('realm selection requires the same deployment processes')
    with actor(name):
        t=Trial(out/(name+'_realm'),controller='code')
        try:
            t.receipt['qualified_scope']='Reviewed realm selection inputs only; world entry requires separate screenshot review'
            t.receipt['lobby_inputs']=[]
            for label,action in [('realm',{'kind':'click','value':[465,182]}),
                                 ('realm_okay',{'kind':'key','value':'Return','hold':.4})]:
                frame=shot(t.out/(label+'_before.png'));t.execute(action)
                t.receipt['lobby_inputs'].append({'label':label,'input':action,'before_frame':frame});t.persist()
            t.receipt['read_only_lobby_settling_seconds']=12;t.persist();time.sleep(12)
            t.receipt['next_screen']=shot(t.out/'next_screen.png')
            t.receipt.update(completed=True,requires_character_selection_review=True)
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({'actor':name,'inputs_completed':t.receipt['completed'],'failure':t.receipt['failure'],
            'requires_separate_character_selection_review':True}),flush=True)
        if not t.receipt['completed']:raise RuntimeError(t.receipt['failure'])


def recovery(source,out,name,client_restart_source=None,observer_version=None):
    """Prepare a new lobby receipt after a failed input on the same deployment."""
    previous=json.loads((source/'deployment.json').read_text())
    if identity('worldserver')!=previous['native'] or identity('modern_world')!=previous['after']:
        raise RuntimeError('recovery requires the same verified deployment processes')
    if client_restart_source:
        restart_path=client_restart_source.resolve()
        if not restart_path.is_relative_to(lab.ROOT/'evidence'):raise ValueError('require an owned client restart receipt')
        restart=json.loads(restart_path.read_text())
        old_path=next((source/(name+suffix)/'episode.json' for suffix in ['_after','_login','_before']
            if (source/(name+suffix)/'episode.json').is_file()),None)
        if old_path is None:raise RuntimeError('owned deployment has no prior client lifetime receipt')
        old=json.loads(old_path.read_text())
        lifetime=lambda row:{key:row[key] for key in ['pid','start_ticks']}
        if (not restart.get('finished_at') or not restart.get('launched') or restart['actor']!=name or
            restart['native']!=previous['native'] or restart['bridge']!=previous['after'] or
            lifetime(restart['before_client'])!=lifetime(old['runtime']['client']) or
            lifetime(restart['after_client'])!=lifetime(lab.owned_process('client')) or not old.get('finished_at')):
            raise RuntimeError('owned client restart does not bind the prior trial and current runtime')
    elif not previous['reconnected'].get(name,{}).get('completed'):
        raise RuntimeError('recovery requires a previously verified actor entry')
    out.mkdir(exist_ok=False,parents=True,mode=0o700)
    report={key:previous[key] for key in ['schema','native','after','observer_version','baselines']}
    report.update(started_at=time.time(),reconnected={},recovery_source=str(source),native_unchanged=True)
    if client_restart_source:
        report['client_restart_source']={'file':str(restart_path),'sha256':lab.sha256(restart_path)}
        report['prior_client_lifetime_receipt']={'file':str(old_path),'sha256':lab.sha256(old_path)}
    with actor(name):
        if observer_version is not None:
            path=lab.client_root()/'client/_whitemane-60895_/Interface/AddOns/ClientMovementHarness/ClientInteractions.lua'
            import re
            matches=re.findall(r'\bobserver_version=(\d+)\b',path.read_text())
            if matches!=[str(observer_version)]:raise RuntimeError('requested observer version differs from the installed file')
            report['observer_version']=observer_version
            report['installed_observer_source']={'file':str(path),'sha256':lab.sha256(path)}
        report['lobby_frames']={name:shot(out/(name+'_disconnected.png'))}
    lab.private_write(out/'deployment.json',json.dumps(report,indent=2)+'\n')
    print(json.dumps({'lobby_frames':report['lobby_frames'],'requires_separate_visual_review':True}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['restart','reconnect','recovery','select-realm','resume-login','dismiss-dialog','resume-after-dismiss'])
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--version',type=int)
    parser.add_argument('--actor',choices=['primary','scout']);parser.add_argument('--source',type=Path)
    parser.add_argument('--keyboard-modal',action='store_true',help='Use Return for the reviewed default modal/entry buttons')
    parser.add_argument('--unavailable-primary-source',type=Path,help='Closed failed reentry baseline for a disconnected primary')
    parser.add_argument('--unavailable-scout-source',type=Path,help='Closed failed scout reentry deployment')
    parser.add_argument('--unavailable-deployment-source',type=Path,help='Failed deployment on the same verified actor/server lifetimes')
    parser.add_argument('--character-selection',action='store_true',help='Reviewed actor is already at character selection; only enter')
    parser.add_argument('--disconnect-screen',action='store_true',help='Reviewed owned disconnect dialog; only click Reconnect')
    parser.add_argument('--login-attempt',type=int,choices=[1,2],default=1,help='Second attempt requires separate unchanged-dialog review')
    parser.add_argument('--realm-selection',action='store_true',help='Reviewed actor is already at realm selection; select the lab realm then enter')
    parser.add_argument('--client-restart-source',type=Path,help='Owned restart receipt binding a failed trial to the new client lifetime')
    parser.add_argument('--combat-source',type=Path,help='Closed failed combat episode with the exact pending native helmet relocation')
    args=parser.parse_args()
    # Recovery reads the baseline from the already verified original deployment.
    if args.action=='restart':
        if args.version is None:parser.error('restart requires the expected observer version')
        restart(args.output,args.version,args.unavailable_primary_source,args.unavailable_scout_source,args.unavailable_deployment_source,args.combat_source)
    elif args.action=='recovery':
        if args.actor is None or args.source is None:parser.error('recovery requires an actor and source deployment')
        with actor(args.actor):recovery(args.source,args.output,args.actor,args.client_restart_source,args.version)
    elif args.action in ['resume-login','dismiss-dialog','resume-after-dismiss']:
        if args.actor is None or not args.disconnect_screen:parser.error('login resumption requires actor and reviewed disconnect screen')
        resume_login(args.output,args.actor,args.login_attempt,args.action=='dismiss-dialog',args.action=='resume-after-dismiss',args.keyboard_modal)
    elif args.action=='select-realm':
        if args.actor is None:parser.error('realm selection requires an actor')
        select_realm(args.output,args.actor)
    else:
        if args.actor is None:parser.error('reconnect requires an actor')
        reconnect(args.output,args.actor,args.keyboard_modal,args.character_selection,args.realm_selection)
