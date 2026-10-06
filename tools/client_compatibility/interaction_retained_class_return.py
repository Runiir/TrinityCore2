"""Return to the retained trained class without an unnecessary bridge restart."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_bridge_deploy import shot
from .interaction_retained_class_fixture import closed
from .interaction_owned_class_fixture import character,saved,pets,origin_checks,SCRIPT_BOUNDARY
from .interaction_pet_control_training import protected


def continuity(current,fixture,old,park,finish,preparation_sha):
    if (fixture.get('guid')!=2 or old.get('origin_actor')!=fixture or old.get('actor')!=fixture or
        old.get('phase')!='await_owned_class_lobby_review' or
        tuple(old.get('class_actor',{}).get(k) for k in ('guid','account_id','character_name','race','class','level'))
            !=(5,2,'Harnessctrl',1,9,10) or
        any(d.get('runtime')!=current for d in (old,park,finish)) or
        park.get('actor')!=old['class_actor'] or finish.get('actor')!=fixture or
        park.get('phase')!='await_original_selection_review' or
        any(d.get('fixture_source',{}).get('sha256')!=preparation_sha for d in (park,finish)) or
        len(park.get('checks',{}))!=4 or not all(park['checks'].values()) or
        len(finish.get('checks',{}))!=5 or not all(finish['checks'].values()) or
        park.get('retained_class_fixture',{}).get('online')!=0):
        raise RuntimeError('closed same-runtime trained fixture return differs')


def prepare(t,preparation,parked,origin_finish):
    old,park,finish=[closed(p) for p in (preparation,parked,origin_finish)]
    continuity(t.receipt['runtime'],t.fixture,old,park,finish,lab.sha256(preparation))
    checks=protected(old);checks.update(retained_character=character(5,2)==park['retained_class_fixture'],
        retained_saved=saved(5)==park['retained_class_saved'],retained_pet=pets(5)==park['retained_class_pets'],
        origin_registration=actors.load()==t.fixture)
    if not all(checks.values()):raise RuntimeError('retained trained or protected fixture changed')
    t.receipt.update(sources=[{'path':str(p.resolve()),'sha256':lab.sha256(p)} for p in (preparation,parked,origin_finish)],
        origin_actor=old['origin_actor'],origin_native=old['origin_native'],origin_saved=old['origin_saved'],
        origin_roster=old['origin_roster'],class_actor=old['class_actor'],natural_native=park['retained_class_fixture'],
        natural_saved=park['retained_class_saved'],retained_class_pets=park['retained_class_pets'],
        retained_level_one=old['retained_level_one'],checks=checks,
        qualified_scope='Same-runtime retained trained fixture registration and read-only lobby capture only; no gameplay qualification.')
    t.persist()
    if actors.register(5)!=old['class_actor']:raise RuntimeError('trained actor registration differs')
    t.receipt.update(completed=True,phase='await_owned_class_lobby_review',frame=shot(t.out/'owned_lobby.png'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('preparation','park','origin-finish','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code');t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:prepare(t,a.preparation,a.park,a.origin_finish)
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('phase','completed','failure')}),flush=True)
