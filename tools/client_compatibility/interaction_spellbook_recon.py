"""Capture owned stock spellbook controls before testing their contents."""
import argparse,json,time
from pathlib import Path
from . import actors
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_operations import controls,click_case
from .interaction_macros import require
from .observation.inventory import Inventory
from . import lab_runtime as lab


def resources(oracle):
    oracle.poll()
    return {'money':oracle.money(),'equipment':[oracle.equipment(i) for i in range(1,20)],
        'backpack':[oracle.slot(0,i) for i in range(1,17)],
        'bags':[[oracle.slot(b,i) for i in range(1,37)] for b in range(1,5)]}


def suite(t):
    session=actors.session_entry(t.fixture)['session'];oracle=Inventory(lab.ROOT,session,t.fixture['guid']).poll()
    t.clean_panels();original=resources(oracle)
    t.receipt.update(native_session=session,baseline=original,
        qualified_scope='Stock spellbook opening/control reconnaissance only; tab contents, paging, tooltips and spell actions remain unqualified')
    t.persist()
    try:
        require(click_case(t,'spellbook.recon.open','Open the stock spellbook with its observed microbutton.',
            lambda c:c['name']=='SpellbookMicroButton',
            lambda b,a,s:{'status':'spellbook_open_pass' if s and 'SpellBookFrame' in a['panels'] and
                not a.get('lua_errors') and not a.get('blocked_actions') else 'client_or_protocol_failure'},
            await_state=lambda a:'SpellBookFrame' in a['panels']),'spellbook_open_pass')
        state,frame=t.observe('stock_spellbook')
        t.receipt['spellbook_controls']=controls(t)
        t.receipt['spellbook_observation']={'state':state,'frame':frame};t.persist()
    finally:
        try:t.clean_panels()
        finally:
            t.receipt['native_after']=resources(oracle)
            t.receipt['native_resources_preserved']=t.receipt['native_after']==original;t.persist()
            if not t.receipt['native_resources_preserved']:raise RuntimeError('spellbook reconnaissance changed native inventory/money')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--actor',choices=['primary','scout'],required=True);a=p.parse_args()
    with actor(a.actor):
        t=Trial(a.output,controller='code')
        try:suite(t);t.receipt['completed']=True
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
        finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
