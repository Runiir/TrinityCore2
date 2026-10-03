"""Verify a stock watched faction across UI reload, then restore the whole baseline."""
import argparse,json,time
from pathlib import Path
from . import actors
from .interaction_trial import Trial
from .interaction_reputation import open_panel,catalog,detail,native_state,native_catalog,standing_oracle,inspect_stormwind
from .interaction_reputation_controls import watch
from .interaction_trade import inventory
from .interaction_macros import require


def suite(t):
    actors.session_entry(t.fixture);t.clean_panels();baseline,items=native_state(),inventory()
    if baseline['character'][2]!=0xffffffff:raise RuntimeError('requires no originally watched faction')
    t.receipt['baseline']={'native':baseline,'inventory_money':items};t.persist();public=None
    try:
        open_panel(t);public=catalog(t,'persist_baseline');native=native_catalog(baseline)
        standing_oracle(public,native);t.receipt['public_baseline']=public;t.persist()
        inspect_stormwind(t,public,native,'reputation.persist_select')
        watch(t,True,'persist_setup',baseline,native[72])
        expected={**baseline,'character':(*baseline['character'][:2],native[72]['index'])}
        def outcome(b,a,s):
            probe=detail(t,'watch_after_reload');saved=native_state();bar=probe.get('watch_bar',{})
            watched=probe.get('watched',{});visible=next(r['visible'] for r in probe['controls'] if r['name']=='ReputationWatchBar')
            span=watched.get('max',0)-watched.get('min',0)
            value=watched.get('value',0)-watched.get('min',0)
            checks={'watch_identity_value':(watched.get('id'),watched.get('value'))==(72,native[72]['value']),
                'watch_bar_visible':visible,'watch_bar_values':(bar.get('min'),bar.get('max'),bar.get('value'))==(0,span,value),
                'native_watch_preserved':saved==expected,'inventory_money_preserved':inventory()==items,
                'public_character_preserved':all(a.get(k)==b.get(k) for k in ['guid','money','equipment','group','raid_profile']),
                'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
            oracle={'public':probe,'native':saved,'checks':checks,'passed':s=='reload' and all(checks.values())}
            t.receipt['persistence_oracle']=oracle;t.persist()
            return {'status':'reputation_persistence_pass' if oracle['passed'] else 'client_or_protocol_failure','oracle':oracle}
        require(t.step('reputation.persist_reload','Reload the interface and keep Stormwind watched.',
            {'reload':{'kind':'chat','value':'/reload','description':'Use the ordinary /reload command.'}},outcome,
            diagnostic_action='reload'),'reputation_persistence_pass')
    finally:
        current=native_state()
        if current['character'][2]!=baseline['character'][2]:
            state,_=t.observe('persist_cleanup_state')
            if 'ReputationFrame' not in state['panels']:open_panel(t)
            current_public=catalog(t,'persist_cleanup_catalog')
            inspect_stormwind(t,current_public,native_catalog(baseline),'reputation.persist_cleanup_select')
            watch(t,False,'persist_restore',baseline,native_catalog(baseline)[72])
        restored=catalog(t,'persist_restored') if public else None
        t.clean_panels();checks={'native_reputation_restored':native_state()==baseline,
            'inventory_money_unchanged':inventory()==items,'public_catalog_restored':not public or restored['rows']==public['rows']}
        t.receipt['restoration']=checks;t.persist()
        if not all(checks.values()):raise RuntimeError('watched-faction reload did not restore its full baseline')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    t=Trial(a.output,controller='code')
    try:suite(t);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:
        t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
