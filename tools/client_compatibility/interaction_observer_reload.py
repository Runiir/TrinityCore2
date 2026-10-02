"""Deploy the read-only observer and verify its version on each owned client."""
import argparse,json,shutil,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial


def reload(out,version):
    out.mkdir(exist_ok=False,parents=True,mode=0o700)
    for name in ['primary','scout']:
        with actor(name):
            source=lab.REPO/'tools/client_compatibility/observation/addon/ClientMovementHarness'
            shutil.copytree(source,lab.client_root()/'client/_whitemane-60895_/Interface/AddOns/ClientMovementHarness',dirs_exist_ok=True)
            t=Trial(out/name,controller='code')
            try:
                t.clean_panels();t.execute({'kind':'chat','value':'/reload'});s,f=t.observe('observer_reloaded')
                t.receipt['observation']={'version':s.get('observer_version'),'frame':f,
                    'lua_errors':s.get('lua_errors'),'blocked_actions':s.get('blocked_actions')}
                if s.get('observer_version')!=version or s.get('lua_errors') or s.get('blocked_actions'):
                    raise RuntimeError('observer reload failed its read-only version/error checks')
                t.receipt['completed']=True
            except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
            finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'actor':name,'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
            if not t.receipt['completed']:raise RuntimeError(t.receipt['failure'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--version',type=int,required=True);a=p.parse_args();reload(a.output,a.version)
