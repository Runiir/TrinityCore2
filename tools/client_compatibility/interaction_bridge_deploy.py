"""Restart only the owned bridge, then reconnect reviewed lobby screens on HDMI-1."""
import argparse
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


def restart(out,version):
    out.mkdir(exist_ok=False,parents=True,mode=0o700)
    native=identity('worldserver'); before=identity('modern_world'); control.native_command()
    baselines={}
    for name in ['primary','scout']:
        with actor(name):
            t=Trial(out/(name+'_before'),controller='code')
            try:
                actors.session_entry(t.fixture);t.clean_panels();state,frame=t.observe('before_deploy')
                baselines[name]={key:state.get(key) for key in ['guid','money','equipment','group','raid_profile']}
                t.receipt['baseline']={'state':state,'frame':frame};t.receipt['completed']=True
                shutil.copytree(lab.REPO/'tools/client_compatibility/observation/addon/ClientMovementHarness',
                    lab.client_root()/'client/_whitemane-60895_/Interface/AddOns/ClientMovementHarness',dirs_exist_ok=True)
            finally: t.receipt['finished_at']=time.time();t.persist()
    report={'schema':'client442_bridge_deployment_v1','started_at':time.time(),'native':native,'before':before,
            'observer_version':version,'baselines':baselines,'reconnected':{}}
    lab.private_write(out/'deployment.json',json.dumps(report,indent=2)+'\n')
    lab.stop('modern_world');control.start();report['after']=identity('modern_world')
    if identity('worldserver')!=native: raise RuntimeError('native worldserver changed during bridge deployment')
    report['native_unchanged']=True
    for name in ['primary','scout']:
        with actor(name): report.setdefault('lobby_frames',{})[name]=shot(out/(name+'_disconnected.png'))
    lab.private_write(out/'deployment.json',json.dumps(report,indent=2)+'\n')
    print(json.dumps({'native_unchanged':True,'lobby_frames':report['lobby_frames']}),flush=True)


def reconnect(out,name):
    report=json.loads((out/'deployment.json').read_text())
    if identity('worldserver')!=report['native'] or identity('modern_world')!=report['after']:
        raise RuntimeError('deployment process identity changed')
    if name in report['reconnected']:raise RuntimeError('actor already reconnected in this deployment')
    # These are the ordinary lobby controls from the separately captured and
    # visually reviewed 1280x720 client screens. Stop on any observation failure.
    inputs=[('okay',[640,380],.4),('reconnect',[640,418],3),('realm',[465,182],.4),
            ('realm_okay',[750,570],3),('enter',[640,661],10)]
    with actor(name):
        t=Trial(out/(name+'_after'),controller='code')
        try:
            t.receipt['lobby_inputs']=[]
            for label,point,delay in inputs:
                frame=shot(t.out/(label+'_before.png'))
                t.io.click(*point);time.sleep(delay)
                t.receipt['lobby_inputs'].append({'source':'code_fixture_reconnect','label':label,'point':point,'before_frame':frame})
                t.persist()
            state,frame=t.observe('reconnected');entry=actors.session_entry(t.fixture)
            restored=all(state.get(key)==value for key,value in report['baselines'][name].items())
            if (state.get('observer_version')!=report['observer_version'] or state.get('lua_errors') or
                    state.get('blocked_actions') or not restored):
                raise RuntimeError('reconnected observer, resources, equipment or group baseline differs')
            t.clean_panels();t.receipt.update(completed=True,observation={'state':state,'frame':frame,'session':entry['session']})
            report['reconnected'][name]={'session':entry['session'],'completed':True,'frame':frame}
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:
            t.receipt['finished_at']=time.time();t.persist()
            if len(report['reconnected'])==2:report['finished_at']=time.time()
            lab.private_write(out/'deployment.json',json.dumps(report,indent=2)+'\n')
            print(json.dumps({'actor':name,'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
        if not t.receipt['completed']:raise RuntimeError(t.receipt['failure'])


def recovery(source,out,name):
    """Prepare a new lobby receipt after a failed input on the same deployment."""
    previous=json.loads((source/'deployment.json').read_text())
    if identity('worldserver')!=previous['native'] or identity('modern_world')!=previous['after']:
        raise RuntimeError('recovery requires the same verified deployment processes')
    if not previous['reconnected'].get(name,{}).get('completed'):
        raise RuntimeError('recovery requires a previously verified actor entry')
    out.mkdir(exist_ok=False,parents=True,mode=0o700)
    report={key:previous[key] for key in ['schema','native','after','observer_version','baselines']}
    report.update(started_at=time.time(),reconnected={},recovery_source=str(source),native_unchanged=True)
    with actor(name):report['lobby_frames']={name:shot(out/(name+'_disconnected.png'))}
    lab.private_write(out/'deployment.json',json.dumps(report,indent=2)+'\n')
    print(json.dumps({'lobby_frames':report['lobby_frames'],'requires_separate_visual_review':True}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['restart','reconnect','recovery'])
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--version',type=int)
    parser.add_argument('--actor',choices=['primary','scout']);parser.add_argument('--source',type=Path);args=parser.parse_args()
    # Recovery reads the baseline from the already verified original deployment.
    if args.action=='restart':
        if args.version is None:parser.error('restart requires the expected observer version')
        restart(args.output,args.version)
    elif args.action=='recovery':
        if args.actor is None or args.source is None:parser.error('recovery requires an actor and source deployment')
        recovery(args.source,args.output,args.actor)
    else:
        if args.actor is None:parser.error('reconnect requires an actor')
        reconnect(args.output,args.actor)
