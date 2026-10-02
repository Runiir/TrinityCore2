"""Bounded real-client fixture diagnostics, separate from learned gameplay policies."""
import argparse
import json
import math
from pathlib import Path
import subprocess
import time
from . import lab_runtime as lab,actors,owned_input,archaeology_inputs,ground_navigation
from .observation.transport import Observer


def run(out,mode):
    out.mkdir(parents=True,exist_ok=False,mode=0o700)
    fixture=actors.load();observer=Observer();monitor=owned_input.focus()
    if observer.guid!=fixture['guid']:raise RuntimeError('probe observer and actor fixture disagree')
    receipt={'schema':'client442_actor_probe_v1','started_at':time.time(),'actor':fixture,'monitor':monitor,
        'mode':mode,'controller':'bounded_code_fixture_diagnostic','laya_called':False,
        'code_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=lab.REPO,text=True).strip(),
        'steps':[],'frames':[],'completed':False,'failure':None}
    latest=out/'latest.png';before=None
    try:
        for index in range(6):
            movement,extra=archaeology_inputs.screenshot(latest);facts=observer.poll()
            if not movement['in_world'] or movement['health_percent']<50 or any(
                movement[k] for k in ['dead','in_combat','on_taxi']):raise RuntimeError('unsafe actor probe state')
            if facts['session']!=observer.session:raise RuntimeError('actor session changed during probe')
            if before is None:before=facts['position'][:]
            if facts['map']!=extra['world_map']:raise RuntimeError('client and owned session maps disagree')
            if math.dist(before[:2],facts['position'][:2])>3:raise RuntimeError('probe left its three-yard fixture envelope')
            frame=out/f'step_{index:03d}.png';latest.replace(frame)
            receipt['frames'].append({'file':frame.name,'sha256':lab.sha256(frame)})
            step={'time':time.time(),'movement':movement,'travel':extra,'facts':facts,'input':None}
            receipt['steps'].append(step)
            if mode=='movement' and index==1:
                if any(extra[k] for k in ['mounted','flying','falling','swimming','indoors']):
                    raise RuntimeError('movement fixture requires grounded outdoor feet')
                start=facts['position'];heading=start[3]
                end=[start[0]+math.cos(heading)*1.05,start[1]+math.sin(heading)*1.05,start[2]]
                step['public_ground_guard']=ground_navigation.safe_walk_segment(facts['map'],start,end)
                owned_input.Inputs().key('w',hold=.15);step['input']={'key':'w','hold_seconds':.15}
            lab.private_write(out/'episode.json',json.dumps(receipt,indent=2)+'\n')
            time.sleep(2)
        after=observer.poll()['position']
        if mode=='movement' and math.dist(before[:2],after[:2])<.25:
            raise RuntimeError('bounded physical movement did not produce normal movement packets')
        # Diagnostic save only, not gameplay control. Native saved coordinates
        # verify handler acceptance instead of trusting the client's own packet.
        lab.server_command('saveall');time.sleep(1)
        with lab.connection() as connection,connection.cursor() as cursor:
            cursor.execute('SELECT map,position_x,position_y,position_z FROM client442_characters.characters WHERE guid=%s AND account=%s',
                (fixture['guid'],fixture['account_id']));native=cursor.fetchone()
        if not native or native[0]!=observer.map or math.dist(native[1:],after[:3])>1:
            raise RuntimeError('native saved position does not confirm the observed actor pose')
        receipt.update(completed=True,native_saved_position=list(native),diagnostic_console_command='saveall')
    except (Exception,KeyboardInterrupt) as error:receipt['failure']=f'{type(error).__name__}: {error}'
    finally:
        receipt['finished_at']=time.time();lab.private_write(out/'episode.json',json.dumps(receipt,indent=2)+'\n')
        print(json.dumps({'completed':receipt['completed'],'failure':receipt['failure']}),flush=True)
    return receipt


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--mode',choices=['observe','movement'],required=True);a=p.parse_args();run(a.output.resolve(),a.mode)


if __name__=='__main__':main()
