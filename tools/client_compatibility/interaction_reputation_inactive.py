"""Move an existing faction to inactive and back using the stock checkbox."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_reputation import open_panel,detail,catalog,native_state,native_catalog,standing_oracle,inspect_stormwind
from .interaction_operations import click_case
from .interaction_macros import require
from .interaction_trade import inventory
from .interaction_reputation_navigation import select_inactive,restore_headers


def expected_native(baseline,inactive):
    rows=[(id,value,flags|32 if inactive else flags&~32) if id==72 else (id,value,flags)
        for id,value,flags in baseline['rows']]
    return {**baseline,'rows':tuple(rows)}


def toggle(t,inactive,label,baseline):
    before=detail(t,'inactive_pre_'+label)
    if before.get('selected',{}).get('id')!=72:
        raise RuntimeError('inactive click must target the selected Stormwind detail')
    def outcome(b,a,s):
        probe=detail(t,'inactive_'+label);native=native_state()
        checked=next((r['checked'] for r in probe['controls'] if r['name']=='ReputationDetailInactiveCheckbox'),None)
        hidden=not next(r['visible'] for r in probe['controls'] if r['name']=='ReputationDetailFrame')
        expected=expected_native(baseline,inactive)
        # When the destination header is expanded the engine updates the
        # selected index. A collapsed destination clears it and hides detail.
        selected=probe.get('selected') or {}
        retained=selected.get('id')==72 and selected.get('inactive')==inactive and not hidden
        cleared=probe.get('selected_index')==0 and hidden
        passed=s and (retained or cleared) and checked==inactive and native==expected
        oracle={'public':probe,'native':native,'expected_native':expected,'selection_cleared':cleared,
            'selection_updated':retained,'passed':bool(passed)}
        t.receipt.setdefault('inactive_oracles',{})[label]=oracle;t.persist()
        return {'status':'reputation_inactive_pass' if passed else 'client_or_protocol_failure','oracle':oracle}
    require(click_case(t,'reputation.inactive.'+label,('Move Stormwind to inactive' if inactive else 'Restore Stormwind to active')+'.',
        lambda c:c['name']=='ReputationDetailInactiveCheckbox',outcome),'reputation_inactive_pass')


def suite(t):
    actors.session_entry(t.fixture);t.clean_panels();before,items=native_state(),inventory()
    if next(r[2] for r in before['rows'] if r[0]==72)&32:
        raise RuntimeError('requires the originally active Stormwind reputation')
    t.receipt['baseline']={'native':before,'inventory_money':items};t.persist();public=None
    try:
        open_panel(t);public=catalog(t,'inactive_baseline');native=native_catalog(before);standing_oracle(public,native)
        t.receipt['public_baseline']=public;t.persist()
        inspect_stormwind(t,public,native,'reputation.inactive_select')
        toggle(t,True,'move',before);select_inactive(t,native,'move');toggle(t,False,'restore',before)
    finally:
        current=native_state()
        if next(r[2] for r in current['rows'] if r[0]==72)&32:
            select_inactive(t,native_catalog(before),'cleanup');toggle(t,False,'cleanup_restore',before)
        if public:restore_headers(t,public,'restore')
        restored=catalog(t,'inactive_restored') if public else None
        public_ok=not public or restored['rows']==public['rows']
        t.clean_panels();checks={'native_reputation_restored':native_state()==before,
            'inventory_money_unchanged':inventory()==items,'public_catalog_restored':public_ok}
        t.receipt['restoration']=checks;t.persist()
        if not all(checks.values()):raise RuntimeError('inactive checkbox failed exact native/public restoration')


def restore_from(t,source):
    source=source.resolve()
    if not source.is_relative_to(lab.ROOT/'evidence') or source.name!='episode.json':
        raise ValueError('require an owned closed inactive trial')
    run=json.loads(source.read_text());identity=lambda r:{k:r[k] for k in ['pid','start_ticks']}
    if (not run.get('finished_at') or run.get('completed') or not run.get('inactive_oracles',{}).get('move') or
        run['actor']!=t.fixture or any(identity(run['runtime'][kind])!=identity(lab.owned_process(kind))
            for kind in ['worldserver','client'])):
        raise RuntimeError('inactive recovery source does not bind this actor and native lifetime')
    baseline=run['baseline']['native'];baseline={'character':tuple(baseline['character']),
        'rows':tuple(tuple(r) for r in baseline['rows'])}
    actual=native_state();items=inventory();normalized=lambda r:json.loads(json.dumps(r))
    if (actual!=expected_native(baseline,True) or normalized(actual)!=run['inactive_oracles']['move']['native'] or
        normalized(items)!=run['baseline']['inventory_money']):
        raise RuntimeError('current state is not the closed trial\'s isolated inactive mutation')
    actors.session_entry(t.fixture);t.clean_panels();t.receipt.update(
        recovery_source={'file':str(source),'sha256':lab.sha256(source)},restoration_target=baseline,
        baseline={'native':actual,'inventory_money':items});t.persist()
    open_panel(t);select_inactive(t,native_catalog(baseline),'recovery');toggle(t,False,'recovery_restore',baseline)
    restored=restore_headers(t,run['public_baseline'],'recovery_restored')
    t.clean_panels();checks={'source_native_reputation_restored':native_state()==baseline,
        'public_catalog_restored':restored['rows']==run['public_baseline']['rows'],'inventory_money_unchanged':inventory()==items}
    t.receipt['restoration']=checks;t.persist()
    if not all(checks.values()):raise RuntimeError('source inactive baseline remains unrestored')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--restore-source',type=Path);a=p.parse_args()
    t=Trial(a.output,controller='code')
    try:
        if a.restore_source:restore_from(t,a.restore_source)
        else:suite(t)
        t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:
        t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
