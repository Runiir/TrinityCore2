"""Inspect the empty stock equipment manager after a closed successful deletion."""
import argparse,json,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_trial import Trial
from .interaction_equipment_sets import detail,sets
from .interaction_equipment_set_roundtrip import open_manager,restore_display,stable
from .interaction_tooltips import baseline


def suite(t,source):
    source=source.resolve()
    if not source.is_relative_to(lab.ROOT/'evidence') or source.name!='episode.json':raise ValueError('require owned closed deletion episode')
    old=json.loads(source.read_text());original=stable(baseline());saved=stable(sets())
    if (not old.get('completed') or old.get('failure') or not old.get('finished_at') or
        old['actor']!=t.fixture or old['runtime']!=t.receipt['runtime'] or
        old['native_after']!={'native':original,'sets':saved} or saved['rows']):raise RuntimeError('source deletion and current empty native fixture differ')
    t.receipt.update(source={'file':str(source),'sha256':lab.sha256(source)},baseline=original,
        qualified_scope='empty manager rendering after source deletion; no new deletion input');t.persist();collapsed=None
    try:
        collapsed=open_manager(t,'sets.empty');probe=detail(t,'empty_manager')
        state,frame=t.observe('empty_manager_rendered')
        if probe['count']!=0 or probe['sets'] or not probe['manager_visible'] or state.get('lua_errors') or state.get('blocked_actions'):
            raise RuntimeError('stock empty manager or clean UI was not observed')
        t.receipt['empty_manager']={'public':probe,'frame':frame};t.persist()
    finally:
        try:restore_display(t,collapsed)
        finally:
            t.receipt.update(native_after=stable(baseline()),native_sets_after=stable(sets()));t.persist()
    if t.receipt['native_after']!=original or t.receipt['native_sets_after']!=saved:raise RuntimeError('empty inspection changed native resources or set catalog')
    t.receipt['native_resources_preserved']=True


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--source',type=Path,required=True)
    a=p.parse_args();t=Trial(a.output,controller='code')
    try:suite(t,a.source);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
