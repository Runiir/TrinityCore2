"""Restart one owned private client and retain its server and monitor identities."""
import argparse,json,time
from pathlib import Path
from . import lab_runtime as lab
from .auth import control,accounts
from .interaction_bridge_deploy import identity,shot
from .interaction_social import actor


def restart(out,name,reason):
    if not out.resolve().is_relative_to(lab.ROOT/'evidence') or not reason:
        raise ValueError('restart requires private evidence and a reason')
    out.mkdir(exist_ok=False,parents=True,mode=0o700)
    native=identity('worldserver');bridge=identity('modern_world')
    with actor(name):
        report={'schema':'client442_owned_client_restart_v1','started_at':time.time(),'actor':name,
                'before_client':identity('client'),'native':native,'bridge':bridge,'reason':reason}
        report['before_frame']=shot(out/'before.png')
        lab.private_write(out/'restart.json',json.dumps(report,indent=2)+'\n')
        try:
            credentials=json.loads((lab.client_root()/'secrets/game_account.json').read_text())
            account=accounts.check_password(credentials['username'],credentials['password'])
            if not account:raise RuntimeError('local saved account unavailable')
            control.launch('launcher',accounts.issue(account,'launcher'),account['login'])
            if identity('worldserver')!=native or identity('modern_world')!=bridge:
                raise RuntimeError('server lifetime changed')
            report.update(after_client=identity('client'),launched=True,after_frame=shot(out/'after.png'))
        except Exception as error:
            report['failure']=f'{type(error).__name__}: {error}';raise
        finally:
            report['finished_at']=time.time()
            lab.private_write(out/'restart.json',json.dumps(report,indent=2)+'\n')
    print(json.dumps({'actor':name,'launched':report.get('launched',False),'server_identities_unchanged':True,
                      'requires_lobby_review':True}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--actor',choices=['primary','scout'],required=True)
    parser.add_argument('--reason',required=True)
    args=parser.parse_args();restart(args.output,args.actor,args.reason)
