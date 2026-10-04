"""Reload a committed read-only observer on both clients without server restarts."""
import argparse,json,shutil,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_bridge_deploy import identity
from .interaction_social import actor
from .interaction_trial import Trial


def deploy(out,version,with_compatibility=False,names=('primary','scout')):
    if not names or len(set(names))!=len(names) or any(n not in ('primary','scout') for n in names):
        raise ValueError('require unique owned actor names')
    out.mkdir(parents=True,exist_ok=False,mode=0o700)
    runtime={kind:identity(kind) for kind in ['worldserver','modern_world']}
    report={'schema':'client442_observer_deployment_v1','started_at':time.time(),
        'runtime':runtime,'observer_version':version,'completed':False,'actors':{}}
    try:
        for name in names:
            with actor(name):
                t=Trial(out/name,controller='code')
                try:
                    entry=actors.session_entry(t.fixture);t.clean_panels();before,frame=t.observe('before_reload')
                    baseline={k:before.get(k) for k in ['guid','money','equipment','group','raid_profile']}
                    t.receipt['baseline']={'state':before,'frame':frame,'session':entry['session']};t.persist()
                    shutil.copytree(lab.REPO/'tools/client_compatibility/observation/addon/ClientMovementHarness',
                        lab.client_root()/'client/_whitemane-60895_/Interface/AddOns/ClientMovementHarness',dirs_exist_ok=True)
                    if with_compatibility:
                        source=lab.REPO/'tools/client_compatibility/client_addon/Client442Compatibility'
                        target=lab.client_root()/'client/_whitemane-60895_/Interface/AddOns/Client442Compatibility'
                        t.receipt['compatibility_files_before']={f.name:lab.sha256(f) for f in target.iterdir() if f.is_file()}
                        shutil.copytree(source,target,dirs_exist_ok=True)
                        t.receipt['compatibility_files_after']={f.name:lab.sha256(f) for f in target.iterdir() if f.is_file()}
                        t.persist()
                    t.execute({'kind':'chat','value':'/reload'})
                    after,frame=t.observe('reloaded',seconds=180);now=actors.session_entry(t.fixture)
                    unchanged=all(after.get(k)==v for k,v in baseline.items())
                    if (after.get('observer_version')!=version or after.get('lua_errors') or after.get('blocked_actions')
                            or not unchanged or now['session']!=entry['session']):
                        raise RuntimeError('observer reload changed the session or failed baseline/error checks')
                    if any(identity(kind)!=value for kind,value in runtime.items()):
                        raise RuntimeError('server process changed during observer reload')
                    t.receipt.update(completed=True,observation={'state':after,'frame':frame},
                        observer_file_sha256_after=lab.sha256(lab.client_root()/'client/_whitemane-60895_/'
                            'Interface/AddOns/ClientMovementHarness/ClientInteractions.lua'))
                    report['actors'][name]={'completed':True,'session':now['session'],'frame':frame}
                except Exception as e:
                    t.receipt['failure']=f'{type(e).__name__}: {e}';raise
                finally:t.receipt['finished_at']=time.time();t.persist()
        report['completed']=True
    except Exception as e:report['failure']=f'{type(e).__name__}: {e}'
    finally:
        report['finished_at']=time.time();lab.private_write(out/'deployment.json',json.dumps(report,indent=2)+'\n')
        print(json.dumps({'completed':report['completed'],'failure':report.get('failure')}),flush=True)
    if not report['completed']:raise RuntimeError(report['failure'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--version',type=int,required=True)
    p.add_argument('--with-compatibility',action='store_true',help='Deploy committed compatibility UI files and retain their per-actor hashes')
    p.add_argument('--actor',choices=['primary','scout'],action='append',help='Reload only these owned actors; default both')
    a=p.parse_args();deploy(a.output,a.version,a.with_compatibility,a.actor or ('primary','scout'))
