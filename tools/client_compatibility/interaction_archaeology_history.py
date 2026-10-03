"""Inspect earned artifacts and stock history without replaying a failed solve."""
import argparse,json,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_trial import Trial
from .interaction_operations import click_case
from .interaction_macros import require
from .interaction_archaeology_projects import native,open_panel,catalog


def normalized(value):return json.loads(json.dumps(value))


def inspect(t,source):
    original=json.loads(source.read_text());baseline=native()
    checks=original.get('solve_outcome',{}).get('checks',{})
    if original.get('completed') or not checks.get('native_completion'):
        raise RuntimeError('source is not a failed trial with earned native completion')
    if normalized(baseline)!=original.get('native_after'):
        raise RuntimeError('earned native state differs from the pinned failed trial')
    contract=next(r for r in original['project_contracts'] if r['name']=='Draenei')
    t.receipt.update(source={'file':str(source),'sha256':lab.sha256(source)},baseline=baseline,
        earned_project=contract,original_failure_preserved=True);t.persist()
    try:
        t.clean_panels()
        require(t.step('archaeology.artifact_bag','Open the backpack and inspect the earned artifact.',
            {'bag':{'kind':'key','value':'b','description':'Press B to open the backpack.'}},
            lambda b,a,s:{'status':'archaeology_artifact_visible_pass' if 0 in a.get('bags',[]) and
                any(r['id']==contract['item'] and r['count']==1 for r in a.get('bag_items',[])) else
                'client_or_protocol_failure','oracle':{'expected_item':contract['item'],'bag_items':a.get('bag_items')}},
            diagnostic_action='bag'),'archaeology_artifact_visible_pass')
        t.clean_panels();open_panel(t)
        def outcome(b,a,s):
            public=catalog(t,'completed_history');t.receipt['history']=public;t.persist()
            return {'status':'archaeology_history_inspected' if s and public['completed_visible'] else
                'client_or_protocol_failure','oracle':public}
        require(click_case(t,'archaeology.completed_tab','Inspect completed archaeology projects.',
            lambda c:c['name']=='ArchaeologyFrameCompletedButton',outcome),'archaeology_history_inspected')
    finally:
        t.clean_panels();after=native();t.receipt.update(native_after=after,native_unchanged=after==baseline);t.persist()
        if after!=baseline:raise RuntimeError('read-only earned-artifact inspection changed native state')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--source',type=Path,required=True);a=p.parse_args();t=Trial(a.output,controller='code')
    try:inspect(t,a.source);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:
        t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
