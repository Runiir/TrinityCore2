"""Resume a parked owned class without restarting its unchanged bridge."""
import argparse,json,re,shutil,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_bridge_deploy import shot
from .interaction_retained_class_fixture import closed,parking_restored
from .interaction_owned_class_fixture import character,saved,pets,origin_checks,SCRIPT_BOUNDARY


def continuity(t,old,park,finish,preparation_sha):
    parked={'original_character','original_saved_rows','native_worldserver','class_offline'}
    restored=parked|{'origin_registration'}
    fixture=old.get('class_actor',{})
    eligible=(fixture.get('guid')==5 and tuple(fixture.get(k) for k in
        ['character_name','race','class','level','account_id'])==('Harnessctrl',1,9,10,2))
    if (old.get('phase')!='await_owned_class_lobby_review' or
        old.get('origin_actor',{}).get('guid')!=2 or (fixture.get('guid')!=4 and not eligible) or
        old.get('origin_actor')!=t.fixture or old.get('actor')!=t.fixture or
        park.get('actor')!=old.get('class_actor') or finish.get('actor')!=t.fixture or
        any(v.get('runtime')!=t.receipt['runtime'] for v in (old,park,finish)) or
        park.get('phase')!='await_original_selection_review' or
        any(v.get('fixture_source',{}).get('sha256')!=preparation_sha for v in (park,finish)) or
        not (set(park.get('checks',{}))==parked and all(park['checks'].values()) or
            len(park.get('checks',{}))==7 and parking_restored(park)) or
        set(finish.get('checks',{}))!=restored or not all(finish['checks'].values()) or
        not old['finished_at']<=park['started_at']<park['finished_at']<=finish['started_at']<finish['finished_at']):
        raise RuntimeError('closed unchanged-runtime class restoration chain differs')


def install_observer(t,version):
    source=lab.REPO/'tools/client_compatibility/observation/addon/ClientMovementHarness'
    target=lab.client_root()/'client/_whitemane-60895_/Interface/AddOns/ClientMovementHarness'
    match=re.search(r'observer_version=(\d+)',(source/'ClientInteractions.lua').read_text())
    if not match or int(match[1])!=version:
        raise RuntimeError('requested committed observer version differs')
    hashes=lambda directory:{p.name:lab.sha256(p) for p in directory.iterdir() if p.is_file()}
    before=hashes(target);expected=hashes(source)
    shutil.copytree(source,target,dirs_exist_ok=True)
    after=hashes(target)
    if any(after.get(name)!=digest for name,digest in expected.items()):
        raise RuntimeError('parked observer installation differs from committed files')
    t.receipt['parked_observer_installation']={'version':version,'before':before,'after':after,
        'source':expected,'input_sent':False,'load_on':'next ordinary owned class entry'}
    t.persist()


def prepare(t,preparation,parked,origin_finish,observer_version=None):
    sources=[p.resolve() for p in (preparation,parked,origin_finish)]
    old,park,finish=[closed(p) for p in sources]
    continuity(t,old,park,finish,lab.sha256(sources[0]))
    fixture=old['class_actor'];guid=fixture['guid'];account=fixture['account_id']
    checks=origin_checks(old)
    checks.update(class_offline=park['retained_class_fixture']['online']==0,
        retained_character=character(guid,account)==park['retained_class_fixture'],
        retained_saved_rows=saved(guid)==park['retained_class_saved'],
        retained_pets=pets(guid)==park['retained_class_pets'],origin_registration=actors.load()==t.fixture)
    if guid==5:
        retained=old['retained_level_one']
        checks.update(retained_level_one_character=character(4,2)==retained['character'],
            retained_level_one_saved=saved(4)==retained['saved'],retained_level_one_pets=pets(4)==retained['pets'])
    if not all(checks.values()):raise RuntimeError('retained class or original saved state changed')
    t.receipt.update(sources=[{'path':str(p),'sha256':lab.sha256(p)} for p in sources],
        origin_actor=old['origin_actor'],origin_native=old['origin_native'],origin_saved=old['origin_saved'],
        origin_roster=old['origin_roster'],class_actor=fixture,natural_native=park['retained_class_fixture'],
        natural_saved=park['retained_class_saved'],retained_class_pets=park['retained_class_pets'],
        checks=checks,qualified_scope='Unchanged-runtime retained fixture continuity only; no gameplay qualification.')
    t.persist()
    if guid==5:t.receipt['retained_level_one']=old['retained_level_one']
    if observer_version is not None:install_observer(t,observer_version)
    if actors.register(guid)!=fixture:raise RuntimeError('retained class registration differs')
    t.receipt.update(completed=True,phase='await_owned_class_lobby_review',frame=shot(t.out/'owned_lobby.png'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('preparation','park','origin-finish','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--observer-version',type=int,help='Install the committed passive observer while the scout is offline')
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code');t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:prepare(t,a.preparation,a.park,a.origin_finish,a.observer_version)
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('phase','completed','failure')}),flush=True)
