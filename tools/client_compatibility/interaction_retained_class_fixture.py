"""Bind an unchanged retained class fixture to a completed bridge-only deployment."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_bridge_deploy import shot
from .interaction_owned_class_fixture import character,saved,pets,origin_checks,SCRIPT_BOUNDARY


def closed(path):
    path=path.resolve()
    if path.name!='episode.json' or not path.is_relative_to(lab.ROOT/'evidence') or path.is_symlink():
        raise ValueError('requires a private owned closed episode')
    v=json.loads(path.read_text())
    if v.get('completed') is not True or v.get('failure') is not None or not v.get('finished_at'):
        raise RuntimeError('retained fixture source is not closed and successful')
    return v


def parking_restored(park):
    checks=park.get('checks',{})
    if len(checks)==4:return all(checks.values())
    expected={'original_character','original_saved_rows','native_worldserver','class_offline',
        'ordinary_logout','native_logout','delivered_logout'}
    source=park.get('interrupted_source',{});path=Path(source.get('path','')).resolve()
    if (set(checks)!=expected or not all(checks.values()) or park.get('input_sent') is not False or
        path.name!='episode.json' or not path.is_relative_to(lab.ROOT/'evidence') or
        path.is_symlink() or not path.is_file() or lab.sha256(path)!=source.get('sha256')):
        return False
    failed=json.loads(path.read_text())
    return (failed.get('completed') is False and bool(failed.get('finished_at')) and
        failed.get('failure')=='InterruptedError: parking process terminated by SIGTERM (exit 143)' and
        failed.get('actor')==park.get('actor') and failed.get('runtime')==park.get('runtime') and
        failed.get('fixture_source')==park.get('fixture_source'))


def continuity(t,old,park,finish,deployment,preparation_sha):
    previous=old.get('runtime',{});current=t.receipt['runtime']
    fixture=old.get('class_actor',{})
    eligible=tuple(fixture.get(k) for k in
        ['guid','character_name','race','class','level','account_id']) in (
            (5,'Harnessctrl',1,9,10,2),(6,'Harnesshunt',1,3,10,2))
    if (old.get('phase')!='await_owned_class_lobby_review' or
        old.get('origin_actor',{}).get('guid')!=2 or (fixture.get('guid')!=4 and not eligible) or
        old.get('actor')!=t.fixture or old.get('origin_actor')!=t.fixture or
        park.get('actor')!=old.get('class_actor') or finish.get('actor')!=t.fixture or
        park.get('runtime')!=previous or finish.get('runtime')!=previous or
        park.get('phase')!='await_original_selection_review' or
        park.get('fixture_source',{}).get('sha256')!=preparation_sha or
        finish.get('fixture_source',{}).get('sha256')!=preparation_sha or
        not parking_restored(park) or
        len(finish.get('checks',{}))!=5 or not all(finish['checks'].values())):
        raise RuntimeError('retained class and original restoration chain differs')
    if (not deployment.get('completed') or not deployment.get('finished_at') or
        not deployment.get('native_unchanged') or not deployment.get('parked_scout') or
        deployment.get('native')!=previous.get('worldserver') or
        deployment.get('before')!=previous.get('modern_world') or
        deployment.get('after')!=current.get('modern_world') or
        previous.get('modern_world')==current.get('modern_world') or
        previous.get('worldserver')!=current.get('worldserver') or
        previous.get('client')!=current.get('client') or
        set(deployment.get('reconnected',{}))!={'primary','scout'} or
        not all(v.get('completed') for v in deployment['reconnected'].values()) or
        deployment['reconnected']['scout'].get('parked') is not True):
        raise RuntimeError('completed bridge-only lifetime continuity differs')


def prepare(t,preparation,parked,origin_finish,deployment_path,observer_version=None):
    preparation,parked,origin_finish=[p.resolve() for p in (preparation,parked,origin_finish)]
    old,park,finish=[closed(p) for p in (preparation,parked,origin_finish)]
    deployment_path=deployment_path.resolve()
    if deployment_path.name!='deployment.json' or not deployment_path.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('requires the completed owned bridge deployment')
    deployment=json.loads(deployment_path.read_text())
    continuity(t,old,park,finish,deployment,lab.sha256(preparation))
    from .interaction_parked_bridge import bound_restoration
    deployed=closed(bound_restoration(deployment_path.parent,deployment))
    if (deployed.get('actor')!=t.fixture or deployed.get('runtime')!=t.receipt['runtime'] or
        len(deployed.get('restoration_checks',{}))!=5 or not all(deployed['restoration_checks'].values()) or
        deployed.get('parked_native')!=old['origin_native']):
        raise RuntimeError('new deployment has no exact parked original restoration')
    primary=closed(deployment_path.parent/'primary_after/episode.json')
    checks=primary.get('bridge_native_restoration',{}).get('checks',{})
    if len(checks)!=9 or not all(checks.values()):
        raise RuntimeError('deployment has no complete primary native restoration')
    if deployment.get('parked_primary'):
        attempt=deployment.get('parked_reconnect_attempt',{}).get('primary',{})
        if (primary.get('bridge_native_restoration',{}).get('offline') is not True or
            primary.get('input_sent') is not False or primary.get('actor',{}).get('guid')!=1 or
            primary.get('runtime',{}).get('worldserver')!=t.receipt['runtime']['worldserver'] or
            primary.get('runtime',{}).get('modern_world')!=t.receipt['runtime']['modern_world'] or
            attempt.get('sha256')!=lab.sha256(deployment_path.parent/'primary_after/episode.json')):
            raise RuntimeError('offline primary restoration is not bound to this completed deployment')
    checks=origin_checks(old)
    fixture=old['class_actor'];guid=fixture['guid'];account=fixture['account_id']
    checks.update(class_offline=park['retained_class_fixture']['online']==0,
        retained_character=character(guid,account)==park['retained_class_fixture'],
        retained_saved_rows=saved(guid)==park['retained_class_saved'],
        retained_pets=pets(guid)==park['retained_class_pets'],origin_registration=actors.load()==t.fixture)
    if guid==5:
        retained=old['retained_level_one']
        checks.update(retained_level_one_character=character(4,2)==retained['character'],
            retained_level_one_saved=saved(4)==retained['saved'],retained_level_one_pets=pets(4)==retained['pets'])
    if guid==6:
        from .interaction_hunter_fixture import protected
        checks.update(protected(old))
    if not all(checks.values()):raise RuntimeError('retained class or original saved state changed')
    sources=[preparation,parked,origin_finish,deployment_path]
    t.receipt.update(sources=[{'path':str(p),'sha256':lab.sha256(p)} for p in sources],
        origin_actor=old['origin_actor'],origin_native=old['origin_native'],origin_saved=old['origin_saved'],
        origin_roster=old['origin_roster'],class_actor=fixture,natural_native=park['retained_class_fixture'],
        natural_saved=park['retained_class_saved'],retained_class_pets=park['retained_class_pets'],
        checks=checks,qualified_scope='Retained native-account class fixture continuity only; no gameplay qualification.')
    t.persist()
    if guid==5:t.receipt['retained_level_one']=old['retained_level_one']
    if guid==6:t.receipt['protected_baseline']=old['protected_baseline']
    if observer_version is not None:
        from .interaction_retained_class_reentry import install_observer
        install_observer(t,observer_version)
    if actors.register(guid)!=fixture:raise RuntimeError('retained class registration differs')
    t.receipt.update(completed=True,phase='await_owned_class_lobby_review',frame=shot(t.out/'owned_lobby.png'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['preparation','park','origin-finish','deployment','output']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--observer-version',type=int,help='Install the committed scout observer while original and class fixtures are offline')
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code');t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:prepare(t,a.preparation,a.park,a.origin_finish,a.deployment,a.observer_version)
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ['phase','completed','failure']}),flush=True)
