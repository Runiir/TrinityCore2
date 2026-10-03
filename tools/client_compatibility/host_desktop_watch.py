"""Read-only focus/pointer attribution during an owned two-client UI probe."""
import argparse,json,os,time
from pathlib import Path
from Xlib import X,display
from . import lab_runtime as lab


def watch(out):
    report=json.loads((out/'cohort.json').read_text());owned={j['monitor']['window_id'] for j in report['jobs']}
    screen=display.Display(os.environ.get('DISPLAY',':0'));root=screen.screen().root
    data={'schema':'client442_host_desktop_watch_v1','started_at':time.time(),
        'read_only':True,'records':[],'samples':0,'completed':False,'failure':None}
    target=out/'host_desktop_watch.json';deadline=time.monotonic()+240
    try:
        while True:
            active=root.get_full_property(screen.intern_atom('_NET_ACTIVE_WINDOW'),X.AnyPropertyType)
            active=int(active.value[0]) if active is not None and len(active.value) else 0
            pointer=root.query_pointer();value={'active_window':active,'pointer':[pointer.root_x,pointer.root_y]}
            if not data['records'] or any(data['records'][-1][k]!=v for k,v in value.items()):
                data['records'].append({'time':time.time(),**value})
            data['samples']+=1
            episodes=[Path(j['output'])/'episode.json' for j in report['jobs']]
            if all(p.is_file() and json.loads(p.read_text()).get('finished_at') for p in episodes):break
            if time.monotonic()>deadline:raise RuntimeError('UI probe did not close within the desktop observation bound')
            time.sleep(.05)
        data['completed']=True
    except Exception as e:data['failure']=f'{type(e).__name__}: {e}'
    finally:
        screen.close();data['finished_at']=time.time()
        data['host_focus_unchanged']=len({r['active_window'] for r in data['records']})==1
        data['host_pointer_unchanged']=len({tuple(r['pointer']) for r in data['records']})==1
        data['both_clients_background_throughout']=not any(r['active_window'] in owned for r in data['records'])
        data['scope']='Opaque window handles and pointer coordinates only; no host screenshots or keystrokes.'
        lab.private_write(target,json.dumps(data,indent=2)+'\n')
        print(json.dumps({k:v for k,v in data.items() if k!='records'}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    watch(p.parse_args().output)
