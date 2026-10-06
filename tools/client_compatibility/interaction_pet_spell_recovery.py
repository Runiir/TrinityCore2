"""Restore one closed UI132 aura-cleanup failure without replaying its spell click."""
import argparse,copy,json,time
from pathlib import Path
from types import SimpleNamespace
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import prepared,SCRIPT_BOUNDARY
from .interaction_spellbook_pet_recon import entry_source
from .interaction_pet_spell import SpellPresence,restore_spell
from .interaction_pet_react_modes import mode,whole_restore
from .observation.inventory import Inventory
from .interaction_retained_class_fixture import closed


def eligible(d,t,source_hashes):
    cast=[c for c in d.get('cases',[]) if c.get('id')=='pets.spell_cast']
    if (d.get('completed') is not False or not d.get('finished_at')
        or d.get('execution_failure')!='RuntimeError: ordinary pet spell cleanup differs from original state'
        or d.get('failure')!='RuntimeError: native pet reaction-mode restoration differs'
        or d.get('actor')!=t.fixture or t.fixture.get('guid')!=5 or d.get('runtime')!=t.receipt['runtime']
        or [s.get('sha256') for s in d.get('sources',[])]!=source_hashes
        or len(cast)!=1 or cast[0].get('status')!='owned_native_pet_spell_pass'
        or len(cast[0].get('oracle',{}).get('checks',{}))!=22
        or not all(cast[0]['oracle']['checks'].values())
        or d.get('custom_script_permission')!='blocked_by_user' or d.get('softTargetInteract')!=SCRIPT_BOUNDARY
        or d.get('spell_baseline',{}).get('auras')!={}
        or d.get('spell_baseline',{}).get('public_buffs')!=[]
        or d.get('baseline',{}).get('money')!=9354
        or d.get('baseline',{}).get('saved',{}).get('spells')!=[[80388,1,0]]
        or d.get('baseline',{}).get('pet',{}).get('id')!=2):
        raise RuntimeError('closed owned pet spell restoration source differs')
    return d


def bridge_eligible(d,t,old,previous,deployment,source_hashes):
    # Validate the immutable historical failure on its actual recorded runtime;
    # authorize current input separately through the closed deployment chain.
    eligible(d,SimpleNamespace(fixture=t.fixture,receipt={'runtime':d.get('runtime')}),source_hashes)
    current=t.receipt['runtime'];prior=d['runtime']
    if (previous.get('runtime')!=prior or len(previous.get('sources',[]))!=3 or
        previous['sources'][0].get('sha256')!=source_hashes[0] or
        len(old.get('sources',[]))!=4 or not deployment.get('completed') or not deployment.get('finished_at') or
        not deployment.get('native_unchanged') or not deployment.get('parked_scout') or
        deployment.get('native')!=prior.get('worldserver') or
        deployment.get('before')!=prior.get('modern_world') or deployment.get('after')!=current.get('modern_world') or
        prior.get('modern_world')==current.get('modern_world') or
        any(prior.get(k)!=current.get(k) for k in ('worldserver','client')) or
        old.get('natural_saved')!=d['baseline']['saved'] or
        old.get('natural_native',{}).get('money')!=d['baseline']['money'] or
        old.get('class_actor')!=d['actor'] or len(old.get('retained_class_pets',[]))!=1 or
        any(old['retained_class_pets'][0].get(k)!=v for k,v in d['baseline']['pet'].items())):
        raise RuntimeError('closed bridge-bound pet spell recovery continuity differs')
    return d


def run(t,preparation,entry,source,deployment_path=None,remote_review=None):
    old=prepared(t,preparation);session=actors.session_entry(t.fixture)['session']
    e=entry_source(t,entry,session,preparation);source=source.resolve()
    if source.name!='episode.json' or not source.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('requires the closed owned spell failure')
    d=json.loads(source.read_text())
    if deployment_path is None:
        d=eligible(d,t,[lab.sha256(p.resolve()) for p in (preparation,entry)])
        if session!=d.get('native_session'):raise RuntimeError('failed spell native session changed')
    else:
        deployment_path=deployment_path.resolve()
        if (deployment_path.name!='deployment.json' or not deployment_path.is_relative_to(lab.ROOT/'evidence') or
            remote_review is None):raise ValueError('requires closed owned bridge deployment and remote failure review')
        sources=old.get('sources',[])
        if len(sources)!=4 or sources[3].get('sha256')!=lab.sha256(deployment_path):
            raise RuntimeError('current preparation does not bind the recovery deployment')
        previous_path=Path(sources[0]['path']);previous=closed(previous_path)
        if sources[0].get('sha256')!=lab.sha256(previous_path):raise RuntimeError('previous preparation hash differs')
        hashes=[]
        for row in d.get('sources',[]):
            path=Path(row['path']).resolve()
            if path.name!='episode.json' or not path.is_relative_to(lab.ROOT/'evidence') or path.is_symlink():
                raise ValueError('requires immutable owned historical preparation/entry')
            if lab.sha256(path)!=row['sha256']:raise RuntimeError('historical failure source hash differs')
            hashes.append(row['sha256'])
        if len(hashes)!=2:raise RuntimeError('historical failure source count differs')
        bridge_eligible(d,t,old,previous,json.loads(deployment_path.read_text()),hashes)
        remote_review=remote_review.resolve()
        if not remote_review.is_relative_to(lab.ROOT/'evidence') or remote_review.is_symlink():
            raise ValueError('requires private verified remote archive review')
        review=json.loads(remote_review.read_text())
        if (review.get('cloud_verified') is not True or
            review.get('pointer')!='artifacts/client_harness/442_interactions_20261006_132.tar.gz.dvc' or
            review.get('archive_sha256')!='c40031095e41e4aab06f32b1ccdd6f42806ca08607f8a75fe0151c12afded3ce' or
            not any(r.get('sha256')==lab.sha256(source) and r.get('verified') is True and
                r.get('member')==str(source.relative_to(lab.ROOT)) for r in review.get('receipts',[]))):
            raise RuntimeError('closed failed spell is not in the reviewed remote archive')
        t.receipt['bridge_recovery_sources']=[{'path':str(p.resolve()),'sha256':lab.sha256(p)}
            for p in (deployment_path,remote_review,previous_path)]
    t.receipt.update(original_failure={'path':str(source),'sha256':lab.sha256(source)},
        baseline=copy.deepcopy(d['baseline']),native_session=session,
        spell_baseline=copy.deepcopy(d['spell_baseline']),spell_click_replayed=False,qualification_added=False)
    t.persist();o=SpellPresence(session,5,e['started_at']).poll()
    restore_spell(t,o,d['spell_baseline'])
    mode(t,o,3,'fixture.pet_assist_restore')
    whole_restore(t,o,Inventory(lab.ROOT,session,5).poll(),old,d['baseline'])
    t.receipt.update(completed=True,phase='owned_pet_spell_failure_restored',qualified_scope=
        'Ordinary cleanup of one closed failed pet spell lifecycle only; original failed trial remains excluded. '
        'No Blood Pact click replay and no gameplay qualification.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('preparation','entry','source','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--deployment',type=Path);p.add_argument('--remote-review',type=Path)
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code');t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:run(t,a.preparation,a.entry,a.source,a.deployment,a.remote_review)
        except Exception as error:t.receipt.update(completed=False,failure=f'{type(error).__name__}: {error}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('phase','completed','failure','restoration_checks')}),flush=True)
