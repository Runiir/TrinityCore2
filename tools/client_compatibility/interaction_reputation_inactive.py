"""Move an existing faction to inactive and back using the stock checkbox."""
import argparse,json,time
from pathlib import Path
from . import actors
from .interaction_trial import Trial
from .interaction_reputation import open_panel,detail,catalog,native_state,native_catalog,standing_oracle,inspect_stormwind
from .interaction_operations import click_case
from .interaction_macros import require
from .interaction_trade import inventory


def expected_native(baseline,inactive):
    rows=[(id,value,flags|32 if inactive else flags&~32) if id==72 else (id,value,flags)
        for id,value,flags in baseline['rows']]
    return {**baseline,'rows':tuple(rows)}


def toggle(t,inactive,label,baseline):
    def outcome(b,a,s):
        probe=detail(t,'inactive_'+label);selected=probe.get('selected',{});native=native_state()
        checked=next((r['checked'] for r in probe['controls'] if r['name']=='ReputationDetailInactiveCheckbox'),None)
        expected=expected_native(baseline,inactive)
        passed=s and selected.get('id')==72 and selected.get('inactive')==inactive and checked==inactive and native==expected
        oracle={'public':probe,'native':native,'expected_native':expected,'passed':bool(passed)}
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
        toggle(t,True,'move',before);toggle(t,False,'restore',before)
    finally:
        current=native_state()
        if next(r[2] for r in current['rows'] if r[0]==72)&32:toggle(t,False,'cleanup_restore',before)
        restored=catalog(t,'inactive_restored') if public else None
        public_ok=not public or restored['rows']==public['rows']
        t.clean_panels();checks={'native_reputation_restored':native_state()==before,
            'inventory_money_unchanged':inventory()==items,'public_catalog_restored':public_ok}
        t.receipt['restoration']=checks;t.persist()
        if not all(checks.values()):raise RuntimeError('inactive checkbox failed exact native/public restoration')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    t=Trial(a.output,controller='code')
    try:suite(t);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:
        t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
