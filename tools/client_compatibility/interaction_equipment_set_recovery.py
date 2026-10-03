"""Close an exact failed set-deletion trial and restore its earlier display baseline."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_tooltips import baseline
from .interaction_equipment_sets import sets
from .interaction_equipment_set_roundtrip import stable,RENAMED,open_manager,row,public_named,delete_set,restore_display


def load_source(t,path):
    path=path.resolve()
    if not path.is_relative_to(lab.ROOT/'evidence') or path.name!='episode.json':raise ValueError('require owned closed failed trial')
    run=json.loads(path.read_text())
    if (not run.get('finished_at') or run.get('completed') or not run.get('failure') or
        run['actor']!=t.fixture or run['runtime']!=t.receipt['runtime'] or not run.get('native_resources_preserved')):
        raise RuntimeError('failed source does not bind the exact actor/runtime and preserved native resources')
    return run,{'file':str(path),'sha256':lab.sha256(path)}


def suite(t,source,display_source,display_only=False):
    actors.session_entry(t.fixture)
    run,proof=load_source(t,source);display,display_proof=load_source(t,display_source)
    original=stable(baseline());saved=stable(sets())
    required=('character.equipment_set_delete','equipment_set_delete_pass') if display_only else (
        'character.equipment_set_equip','equipment_set_equip_pass')
    if (run['native_after']!={'native':original,'sets':saved} or
        not any((c['id'],c['status'])==required for c in run['cases']) or
        not any(c['id']=='sets.save.expand' and c['status']=='character_expand_pass' for c in display['cases']) or
        display['baseline']['native']!=original):
        raise RuntimeError('recovery source does not prove the isolated deletion failure and original collapsed display')
    t.receipt.update(recovery_source=proof,display_source=display_proof,baseline={'native':original,'sets':saved});t.persist()
    try:
        t.receipt['phase']='display_only' if display_only else 'delete_and_display';t.persist()
        if display_only:
            if saved['rows']:raise RuntimeError('display recovery requires the source deleted catalog')
        else:
            open_manager(t,'sets.recovery');row(t,RENAMED,'sets.recovery.select')
            probe,valid=public_named(t,'recovery_set',RENAMED)
            if not valid:raise RuntimeError('owned renamed set is absent')
            delete_set(t,probe['sets'][0]['id'],original)
    finally:
        try:restore_display(t,True)
        finally:
            t.receipt['native_after']={'native':stable(baseline()),'sets':stable(sets())}
            t.receipt['native_resources_preserved']=t.receipt['native_after']['native']==original;t.persist()
            if not t.receipt['native_resources_preserved']:raise RuntimeError('equipment-set recovery changed native resources')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--display-source',type=Path,required=True)
    p.add_argument('--display-only',action='store_true')
    a=p.parse_args();t=Trial(a.output,controller='code')
    try:suite(t,a.source,a.display_source,a.display_only);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
