"""Deploy passive observer changes with ordinary /reload, without server restarts."""
import argparse
import json
from pathlib import Path
import shutil
import time
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_social import actor
from .interaction_macros import require


def reload(out,version):
    out.mkdir(exist_ok=False,parents=True,mode=0o700)
    native=lab.owned_process('worldserver');bridge=lab.owned_process('modern_world')
    identity=lambda p:{key:p[key] for key in ['pid','start_ticks']}
    report={'schema':'client442_observer_reload_v1','started_at':time.time(),'completed':False,
        'native':identity(native),'bridge':identity(bridge),'version':version}
    try:
        for name in ['primary','scout']:
            with actor(name):
                t=Trial(out/name,controller='code')
                try:
                    actors.session_entry(t.fixture);t.clean_panels();before,frame=t.observe('observer_before')
                    baseline={key:before.get(key) for key in ['guid','money','equipment','group','raid_profile','bag_items']}
                    t.receipt['observer_before']={'state':before,'frame':frame}
                    source=lab.REPO/'tools/client_compatibility/observation/addon/ClientMovementHarness'
                    target=lab.client_root()/'client/_whitemane-60895_/Interface/AddOns/ClientMovementHarness'
                    shutil.copytree(source,target,dirs_exist_ok=True)
                    t.receipt['observer_deployment']={'source_sha256':lab.sha256(source/'ClientInteractions.lua'),
                        'installed_sha256':lab.sha256(target/'ClientInteractions.lua'),'version':version};t.persist()
                    def oracle(b,a,selected):
                        restored=all(a.get(key)==value for key,value in baseline.items())
                        clean=not a.get('lua_errors') and not a.get('blocked_actions')
                        matches=a.get('observer_version')==version
                        return {'status':'observer_reload_pass' if selected=='reload' and restored and clean and matches else
                                ('controller_failure' if selected!='reload' else 'client_or_protocol_failure'),
                                'oracle':{'baseline_restored':restored,'ui_clean':clean,'version_matches':matches}}
                    require(t.step('observer.reload','Reload the updated passive observer.',{
                        'reload':{'kind':'chat','value':'/reload','description':'Reload the interface with /reload.'},
                        'character':{'kind':'key','value':'c','description':'Open equipment.'}},oracle,
                        diagnostic_action='reload'),'observer_reload_pass')
                    t.clean_panels();t.receipt['completed']=True
                except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}';raise
                finally:t.receipt['finished_at']=time.time();t.persist()
        if identity(lab.owned_process('worldserver'))!=report['native'] or identity(lab.owned_process('modern_world'))!=report['bridge']:
            raise RuntimeError('server process changed during observer-only deployment')
        report.update(completed=True,servers_unchanged=True)
    except Exception as error:report['failure']=f'{type(error).__name__}: {error}'
    finally:
        report['finished_at']=time.time();lab.private_write(out/'cohort.json',json.dumps(report,indent=2)+'\n')
        print(json.dumps(report),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--version',type=int,required=True);a=p.parse_args();reload(a.output,a.version)
