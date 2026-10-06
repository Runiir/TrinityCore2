"""Restore one closed UI132 aura-cleanup failure without replaying its spell click."""
import argparse,copy,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import prepared,SCRIPT_BOUNDARY
from .interaction_spellbook_pet_recon import entry_source
from .interaction_pet_spell import SpellPresence,restore_spell
from .interaction_pet_react_modes import mode,whole_restore
from .observation.inventory import Inventory


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


def run(t,preparation,entry,source):
    old=prepared(t,preparation);session=actors.session_entry(t.fixture)['session']
    e=entry_source(t,entry,session,preparation);source=source.resolve()
    if source.name!='episode.json' or not source.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('requires the closed owned spell failure')
    d=eligible(json.loads(source.read_text()),t,[lab.sha256(p.resolve()) for p in (preparation,entry)])
    if session!=d.get('native_session'):raise RuntimeError('failed spell native session changed')
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
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code');t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:run(t,a.preparation,a.entry,a.source)
        except Exception as error:t.receipt.update(completed=False,failure=f'{type(error).__name__}: {error}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('phase','completed','failure','restoration_checks')}),flush=True)
