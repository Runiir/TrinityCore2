"""Read passive stable cache before/after a separately captured ordinary Tame."""
import argparse,json,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import prepared,saved,pets,SCRIPT_BOUNDARY
from .interaction_retained_class_fixture import closed
from .interaction_spellbook_pet_recon import entry_source
from .interaction_hunter_fixture import protected
from .interaction_hunter_stable_slots import bound
from .interaction_observation import read_page
from .interaction_spellbook_recon import resources
from .observation.inventory import Inventory
from .tame_stable_projection import public_rows,prove


def run(t,preparation,entry,action,before_path=None,cast_path=None):
    old=prepared(t,preparation)
    from . import actors
    session=actors.session_entry(t.fixture)['session'];e=entry_source(t,entry,session,preparation)
    if (t.fixture['guid'],t.fixture['class'],t.fixture['level'])!=(6,3,10):
        raise RuntimeError('requires the owned level10 Hunter')
    retained=pets(6);inv=Inventory(lab.ROOT,session,6).poll()
    if resources(inv)!=e['resources'] or saved(6)!=e['entered_saved']:
        raise RuntimeError('Hunter resource or saved baseline differs')
    t.receipt.update(entry_source=bound(entry),native_session=session,retained_pet_before=retained,
        input_sent=True,gameplay_input_sent=False,qualification_added=False);t.persist()
    page,frame=read_page(t,'tame_stable_cache','stables','/tcui stables')
    probe=page['stable_probe'];wire=None
    if action=='before':
        if (len(retained)!=1 or retained[0]['id']!=4 or retained[0]['slot']!=5 or retained[0]['active']!=0 or
                public_rows(probe)!=[(6,'Harnesswolf',10,903)] or probe.get('stable_slots')!=16):
            raise RuntimeError('requires the exact stored Harnesswolf cache and no active pet')
    else:
        before=closed(before_path);cast=closed(cast_path)
        if (before.get('phase')!='owned_tame_stable_baseline' or before.get('runtime')!=t.receipt['runtime'] or
            len(before.get('checks',{}))!=11 or not all(before['checks'].values()) or
            before.get('actor')!=t.fixture or before.get('fixture_source')!=bound(preparation) or
            before.get('entry_source')!=bound(entry) or before.get('native_session')!=session or
            cast.get('phase')!='owned_tame_native_outcome_captured' or cast.get('runtime')!=t.receipt['runtime'] or
            cast.get('actor')!=t.fixture or cast.get('fixture_source')!=bound(preparation) or
            cast.get('entry_source')!=bound(entry) or cast.get('native_session')!=session or
            len(cast.get('capture_checks',{}))!=14 or not all(cast['capture_checks'].values()) or
            not before['finished_at']<cast['started_at']<cast['finished_at']<t.receipt['started_at'] or
            cast.get('capture_disarmed') is not True or retained!=cast['retained_pet_after']):
            raise RuntimeError('requires the whole same-entry baseline and single captured Tame')
        wire=prove(cast,before['public_stable'],probe)
        t.receipt.update(before_source=bound(before_path),cast_source=bound(cast_path))
    checks={'native_saved_pets':pets(6)==retained,'resources':resources(inv.poll())==e['resources'],
        'saved_rows':saved(6)==e['entered_saved'],'passive_observer':page.get('observer_version')==145,
        'ui_clean':not page.get('lua_errors') and not page.get('blocked_actions'),
        'stable_cache':True,**protected(old)}
    t.receipt.update(checks=checks,public_stable=probe,frame=frame,wire_projection=wire,
        completed=all(checks.values()),phase='owned_tame_stable_'+('baseline' if action=='before' else 'projection'),
        qualified_scope='Passive public stable-cache and actual modern Tame projection proof only; admission requires full closure and remote evidence.')
    if not all(checks.values()):raise RuntimeError('stable projection preservation differs')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['before','after'])
    for name in ('preparation','entry','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--before',type=Path);p.add_argument('--cast',type=Path);a=p.parse_args()
    if a.action=='after' and (not a.before or not a.cast):p.error('after requires baseline and captured Tame')
    with actor('scout'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2,chat_open_retry=True)
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:run(t,a.preparation,a.entry,a.action,a.before,a.cast)
        except Exception as e:t.receipt.update(completed=False,failure=f'{type(e).__name__}: {e}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','phase','failure','checks')}),flush=True)
