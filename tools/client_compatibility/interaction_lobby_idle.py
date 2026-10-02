"""Verify owned character-selection keepalive across the native idle deadline."""
import argparse,json,subprocess,time
from pathlib import Path
from contextlib import redirect_stdout
from io import StringIO
from . import actors,lab_runtime as lab,owned_input
from .observation.journal import Cursor


def suite(out,seconds):
    if not 125<=seconds<=180:raise ValueError('idle trial must cross 120 seconds within a bounded window')
    out.mkdir(parents=True,exist_ok=False,mode=0o700)
    fixture=actors.load();cursor=Cursor(lab.ROOT/'logs/modern_world.jsonl');history=list(cursor.poll())
    authenticated=next((x for x in reversed(history) if x.get('event')=='world_authenticated' and x['account_id']==fixture['account_id']),None)
    if not authenticated:raise RuntimeError('owned account has no modern realm session')
    session=authenticated['session']
    if any(x.get('session')==session and x.get('event')=='world_connection_closed' for x in history):
        raise RuntimeError('owned realm is already disconnected')
    if not any(x.get('session')==session and x.get('name')=='SMSG_ENUM_CHARACTERS_RESULT' and x.get('direction')=='to_client' for x in history):
        raise RuntimeError('owned realm has not returned character selection')
    from tools.second_client import ctl
    ctl._launcher_env=lab.client_environment
    report={'schema':'client442_lobby_idle_v1','started_at':time.time(),'actor':fixture,'session':session,
        'controller':'code_fixture_read_only','model':None,'code_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'window_seconds':seconds,'completed':False,'failure':None,'packets':[]}
    def frame(label):
        monitor=owned_input.focus();path=out/(label+'.png')
        with redirect_stdout(StringIO()):ctl.shot(str(path))
        return {'file':path.name,'sha256':lab.sha256(path),'monitor':monitor}
    try:
        report['before_frame']=frame('before');deadline=time.monotonic()+seconds;heartbeat=time.monotonic()
        while time.monotonic()<deadline:
            for row in cursor.poll():
                if row.get('session')!=session:continue
                if row.get('event') in ['world_connection_closed','native_stream_closed']:raise RuntimeError('owned lobby connection closed')
                if row.get('name')=='CMSG_PLAYER_LOGIN':raise RuntimeError('character entered world during the lobby trial')
                if row.get('name') in ['CMSG_PING','SMSG_PONG']:
                    report['packets'].append({k:row[k] for k in ['time','session','name','direction','bytes']})
            if time.monotonic()>=heartbeat:
                lab.private_write(out/'cohort.json',json.dumps(report,indent=2)+'\n');print(json.dumps({'lobby_idle_elapsed':round(time.time()-report['started_at'])}),flush=True)
                heartbeat=time.monotonic()+25
            time.sleep(.5)
        report['after_frame']=frame('after')
        sends=[r for r in report['packets'] if r['name']=='CMSG_PING' and r['direction']=='to_native']
        pongs=[r for r in report['packets'] if r['name']=='SMSG_PONG' and r['direction']=='from_native']
        report['oracle']={'native_ping_count':len(sends),'native_pong_count':len(pongs),
            'native_pong_after_deadline':any(r['time']>report['started_at']+120 for r in pongs)}
        if len(sends)<4 or len(pongs)<4 or not report['oracle']['native_pong_after_deadline']:
            raise RuntimeError('native keepalive did not span the idle deadline')
        report['completed']=True
    except Exception as e:report['failure']=str(e)
    finally:
        report['finished_at']=time.time();lab.private_write(out/'cohort.json',json.dumps(report,indent=2)+'\n')
        print(json.dumps({k:report.get(k) for k in ['completed','failure','oracle']}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--seconds',type=int,default=135)
    args=p.parse_args();suite(args.output,args.seconds)
