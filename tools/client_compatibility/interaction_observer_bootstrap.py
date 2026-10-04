"""Visually reviewed observer reload for the exact UI64 capacity failure only."""
import argparse,json,shutil,time
from pathlib import Path
from PIL import Image
from . import actors,lab_runtime as lab,owned_input
from .interaction_trial import Trial
from .interaction_social import actor
from .interaction_bridge_deploy import shot
from .interaction_bridge_restoration import capture,restore
from .observation.interactions import decode_image
from .observation.telemetry import decode_image as movement


def partial(t,label):
    deadline=time.monotonic()+18
    while True:
        frame=shot(t.out/(label+'.png'))
        try:
            with Image.open(t.out/frame['file']) as im:
                state=decode_image(im);pos=movement(im,x=15,y=15,cell_size=3.75)
            if state.get('guid')!=t.guid or state.get('build')!=60895:
                raise RuntimeError('partial diagnostic identity differs')
            if not pos['in_world'] or pos['in_combat'] or pos['dead'] or pos['on_taxi'] or pos['health_percent']!=100 or pos['speed']!=0:
                raise RuntimeError('observer bootstrap requires the owned healthy idle character')
            if state.get('lua_errors') or state.get('blocked_actions'):raise RuntimeError('partial observer reports errors')
            return state,frame
        except ValueError:
            if time.monotonic()>deadline:raise RuntimeError('owned partial observer did not become readable')
            time.sleep(.23)


def prepare(out,source):
    source=source.resolve()
    if not source.is_relative_to(lab.ROOT/'evidence') or source.name!='party_fixture_recovery02':
        raise ValueError('require exact closed UI64 party recovery failure')
    old=json.loads((source/'primary/episode.json').read_text());co=json.loads((source/'recovery.json').read_text())
    if co['completed'] or not co.get('finished_at') or co['failure']!='RuntimeError: UI observation did not become decodable':
        raise RuntimeError('source is not the closed observer capacity recovery failure')
    t=Trial(out,controller='code')
    try:
        if t.fixture!=old['actor'] or t.receipt['runtime']!=old['runtime']:raise RuntimeError('source owned runtime changed')
        state,frame=partial(t,'before_prepare')
        if state['observer_version']!=79:raise RuntimeError('require the failed in-memory observer79')
        baseline=capture(t);t.receipt.update(bootstrap_baseline=baseline,bootstrap_session=actors.session_entry(t.fixture)['session'],
            source={'file':str(source/'recovery.json'),'sha256':lab.sha256(source/'recovery.json')},before_frame=frame)
        src=lab.REPO/'tools/client_compatibility/observation/addon/ClientMovementHarness'
        target=lab.CLIENT/'Interface/AddOns/ClientMovementHarness'
        shutil.copytree(src,target,dirs_exist_ok=True)
        t.receipt['installed_observer_sha256']=lab.sha256(target/'ClientInteractions.lua');t.persist()
        with owned_input.lease():
            t.io.key('Return',hold=.4);time.sleep(.2);t.io.type('/reload');time.sleep(.2)
        state,frame=partial(t,'pending_reload')
        t.receipt.update(prepared=True,pending_command='/reload',pending_frame=frame,
            qualified_scope='Only exact observer-recovery /reload staging; agent must visually review pending text before submit.')
    except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'prepared':t.receipt.get('prepared',False),'failure':t.receipt['failure']}),flush=True)


def submit(out,reviewed):
    if not reviewed:raise ValueError('require separate visual review of the staged exact /reload')
    old=json.loads((out/'episode.json').read_text())
    if not old.get('prepared') or old.get('failure') or old['pending_command']!='/reload':raise RuntimeError('exact reload was not staged')
    if lab.sha256(out/old['pending_frame']['file'])!=old['pending_frame']['sha256']:raise RuntimeError('reviewed pending frame changed')
    t=Trial(out/'submit',controller='code')
    try:
        if t.fixture!=old['actor'] or t.receipt['runtime']!=old['runtime'] or capture(t)!=old['bootstrap_baseline']:
            raise RuntimeError('staged reload actor or native baseline changed')
        state,frame=partial(t,'reviewed_pending')
        t.receipt['reviewed_pending_source']={'file':str(out/'episode.json'),'sha256':lab.sha256(out/'episode.json')}
        with owned_input.lease():t.io.key('Return',hold=.4)
        state,frame=t.observe('reloaded',seconds=240)
        if state['observer_version']!=80 or actors.session_entry(t.fixture)['session']!=old['bootstrap_session']:
            raise RuntimeError('observer80 or original session differs after reload')
        restore(t,old['bootstrap_baseline']);t.receipt['completed']=True
    except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','submit']);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--source',type=Path);p.add_argument('--reviewed-pending-reload',action='store_true');a=p.parse_args()
    with actor('primary'):
        if a.action=='prepare':prepare(a.output,a.source)
        else:submit(a.output,a.reviewed_pending_reload)
