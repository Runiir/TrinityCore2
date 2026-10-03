"""Restore only a closed watch trial's exact baseline through its stock checkbox."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_reputation import open_panel,detail,catalog,native_state,native_catalog,standing_oracle
from .interaction_reputation_controls import watch,comparable
from .interaction_operations import click_case
from .interaction_macros import require
from .interaction_trade import inventory


def normalized(value):return json.loads(json.dumps(value))


def suite(t,source):
    source=source.resolve()
    if not source.is_relative_to(lab.ROOT/'evidence') or source.name!='episode.json':
        raise ValueError('require an owned closed interaction receipt')
    run=json.loads(source.read_text());identity=lambda row:{k:row[k] for k in ['pid','start_ticks']}
    if (not run.get('finished_at') or run.get('completed') or not run.get('failure') or
        run['actor']!=t.fixture or any(identity(run['runtime'][kind])!=identity(lab.owned_process(kind))
            for kind in ['worldserver','client'])):
        raise RuntimeError('failed watch source does not bind this actor and native lifetime')
    actors.session_entry(t.fixture);t.clean_panels()
    baseline=run['baseline']['native']
    baseline={'character':tuple(baseline['character']),'rows':tuple(tuple(r) for r in baseline['rows'])}
    native=native_catalog(baseline);current=native_state();items=inventory()
    expected={**baseline,'character':(*baseline['character'][:2],native[72]['index'])}
    proof=run.get('watch_oracles',{}).get('show',{})
    if (baseline['character'][2]!=0xffffffff or current!=expected or
        normalized(current)!=proof.get('native') or proof.get('passed') or
        normalized(items)!=run['baseline']['inventory_money']):
        raise RuntimeError('current state is not the source trial\'s isolated failed watch mutation')
    t.receipt.update(recovery_source={'file':str(source),'sha256':lab.sha256(source)},
        baseline={'native':current,'inventory_money':items},restoration_target=baseline)
    t.persist()
    try:
        open_panel(t);public=catalog(t,'recovery_catalog');standing_oracle(public,native)
        if (public.get('watched',{}).get('id'),public.get('watched',{}).get('value'))!=(72,native[72]['value']):
            raise RuntimeError('reconnected client does not show the exact saved watched faction')
        def selected(b,a,s):
            probe=detail(t,'recovery_selected')
            checked=next((r['checked'] for r in probe['controls'] if r['name']=='ReputationDetailMainScreenCheckbox'),False)
            return {'status':'reputation_select_pass' if s and probe.get('selected',{}).get('id')==72 and checked
                else 'client_or_protocol_failure','oracle':probe}
        require(click_case(t,'reputation.recovery_select','Select the failed trial\'s watched Stormwind faction.',
            lambda c:c['text']=='Stormwind' and c['name'].startswith('ReputationBar'),selected),'reputation_select_pass')
        watch(t,False,'recover_failed_trial',baseline,native[72])
        restored=catalog(t,'recovery_restored')
        if comparable(restored['rows'])!=comparable(run['public_baseline']['rows']):
            raise RuntimeError('source public faction catalog was not restored')
    finally:
        t.clean_panels();checks={'source_native_reputation_restored':native_state()==baseline,
            'inventory_money_unchanged':inventory()==items}
        t.receipt['restoration']=checks;t.persist()
        if not all(checks.values()):raise RuntimeError('failed watch baseline remains unrestored')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();t=Trial(a.output,controller='code')
    try:suite(t,a.source);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:
        t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
