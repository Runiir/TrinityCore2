"""Bind an unchanged retained Hunter to the current verified offline boundary."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_retained_class_fixture import closed
from .interaction_owned_class_fixture import character,saved,pets,origin_checks,SCRIPT_BOUNDARY
from .interaction_hunter_fixture import snapshots,inventory
from .interaction_character_creator_probe import roster
from .interaction_bridge_deploy import shot
from .interaction_retained_class_reentry import install_observer


def prepare(t,previous,park,finish,original,primary):
    paths=[previous,park,finish,original,primary]
    old,parked,restored,offline,primary_closed=[closed(p) for p in paths]
    digest=lab.sha256(previous);fixture=old['class_actor'];current=snapshots()
    retained={'native':character(6,2),'saved':saved(6),'pets':pets(6),'inventory':inventory(6)}
    if (t.fixture.get('guid')!=2 or old.get('phase')!='await_owned_class_lobby_review' or
        old.get('actor')!=old.get('origin_actor') or old['origin_actor']!=t.fixture or
        tuple(fixture.get(k) for k in ('guid','character_name','account_id','race','class','level'))!=
        (6,'Harnesshunt',2,1,3,10) or old['runtime']['client']!=t.receipt['runtime']['client'] or
        parked.get('actor')!=fixture or parked.get('phase')!='await_original_selection_review' or
        len(parked.get('checks',{}))!=4 or not all(parked['checks'].values()) or
        restored.get('actor')!=t.fixture or len(restored.get('checks',{}))!=5 or
        not all(restored['checks'].values()) or any(v.get('fixture_source')!=
        {'path':str(previous.resolve()),'sha256':digest} for v in (parked,restored)) or
        not parked['finished_at']<restored['started_at'] or
        offline.get('actor')!=t.fixture or offline.get('runtime')!=t.receipt['runtime'] or
        offline.get('parked_snapshot')!=current['2'] or
        primary_closed.get('actor',{}).get('guid')!=1 or
        len(primary_closed.get('checks',{}))!=7 or not all(primary_closed['checks'].values()) or
        any(primary_closed['runtime'][k]!=t.receipt['runtime'][k] for k in ('worldserver','modern_world'))):
        raise RuntimeError('closed retained Hunter/current offline source authority differs')
    base=primary_closed['baseline'];primary_before=old['protected_baseline']['1']
    changed={k for k,v in primary_before['native'].items() if current['1']['native'][k]!=v}
    allowed={'position_x','position_y','orientation','totaltime','leveltime','logout_time','latency'}
    pose=[current['1']['native'][k] for k in ('position_x','position_y','position_z','orientation','map')]
    guards={'original_character':current['2']['native']==old['origin_native'],
        'original_saved_rows':current['2']['saved']==old['origin_saved'],
        'native_worldserver':primary_closed['runtime']['worldserver']==t.receipt['runtime']['worldserver'],
        'class_offline':retained['native']['online']==0,
        'retained_character':retained['native']==parked['retained_class_fixture'],
        'retained_saved_rows':retained['saved']==parked['retained_class_saved'],
        'retained_pets':retained['pets']==parked['retained_class_pets'],
        'origin_registration':actors.load()==t.fixture,
        'actor_1_unchanged':current['1']['native']==primary_closed['parked_native'] and
            pose==base['position'] and changed<=allowed and
            all(current['1'][k]==base[k]==primary_before[k] for k in ('saved','pets','inventory')),
        **{f'actor_{g}_unchanged':current[g]==old['protected_baseline'][g]==base['protected'][g]
            for g in ('2','3','4','5')}}
    expected_roster=[*old['origin_roster'],[retained['native'][k] for k in
        ('guid','name','race','class','gender','level','online')]]
    prerequisites={'current_retained_snapshot':retained==base['protected']['6'],
        'all_originals_offline':all(row['native']['online']==0 for row in current.values()),
        'exact_roster':not any(r[0]==6 for r in old['origin_roster']) and roster(t)==expected_roster,
        'retained_named_pet':len(retained['pets'])==1 and tuple(retained['pets'][0].get(k) for k in
            ('id','entry','owner','name','renamed','slot'))==(4,42717,6,'Harnesswolf',1,0)}
    t.receipt.update(checks=guards,prerequisite_checks=prerequisites);t.persist()
    if not all(guards.values()) or not all(prerequisites.values()):
        raise RuntimeError('unchanged retained Hunter or current protected saved boundary differs')
    t.receipt.update(origin_actor=t.fixture,origin_native=current['2']['native'],origin_saved=current['2']['saved'],
        origin_roster=old['origin_roster'],class_actor=fixture,natural_native=retained['native'],
        natural_saved=retained['saved'],retained_class_pets=retained['pets'],protected_baseline=current,
        sources=[{'path':str(p.resolve()),'sha256':lab.sha256(p)} for p in paths],checks=guards,
        previous_primary_changed_columns=sorted(changed),current_primary_authority=t.receipt['runtime'],
        input_sent=False,qualification_added=False,
        qualified_scope='Fresh read-only retained Hunter boundary after separately closed primary work. '
            'Original historical receipts stay immutable; no creation, purchase, rename, pose or pet mutation.')
    t.persist();install_observer(t,143)
    if actors.register(6)!=fixture:raise RuntimeError('retained Hunter registration differs')
    t.receipt.update(completed=True,phase='await_owned_class_lobby_review',frame=shot(t.out/'owned_lobby.png'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('previous','park','finish','original','primary','output'):p.add_argument('--'+k,type=Path,required=True)
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code');t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:prepare(t,a.previous,a.park,a.finish,a.original,a.primary)
        except Exception as error:t.receipt.update(completed=False,failure=f'{type(error).__name__}: {error}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure','phase','checks')}),flush=True)
