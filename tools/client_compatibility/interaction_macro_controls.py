"""Observe and roundtrip stock macro controls on an empty owned fixture."""
import argparse,json,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_trial import Trial
from .interaction_keybindings_native import suite as native_suite
from .interaction_operations import controls,click_case
from .interaction_macros import require
from .interaction_observation import read_current_page


def detail(t,label,ready=None):
    state,frame=read_current_page(t,label,'macros',lambda s:s.get('macro_probe') and
        (ready is None or ready(s['macro_probe'])))
    t.receipt.setdefault('macro_details',{})[label]={'state':state,'frame':frame};t.persist()
    return state['macro_probe']


def open_editor(t):
    t.execute({'kind':'chat','value':'/macro'})
    return detail(t,'macro_editor_open',lambda p:p.get('open'))


def recon(t):
    state,_=t.observe('macro_fixture')
    if state.get('macros')!=[0,0] or state.get('test_macro') or state.get('action_probe',{}).get('kind'):
        raise RuntimeError('requires the empty owned macro fixture and action probe')
    t.receipt['macro_baseline']=state;t.persist()
    open_editor(t)
    t.receipt['macro_editor_controls']=controls(t);t.persist()
    require(click_case(t,'fixture.new_macro_popup','Open the stock new-macro dialog.',
        lambda c:c['name']=='MacroNewButton',lambda b,a,s:{'status':'macro_popup_pass' if s and
            'MacroPopupFrame' in a['panels'] else 'client_or_protocol_failure'}),'macro_popup_pass')
    detail(t,'new_macro_popup',lambda p:p['popup']['visible'])
    t.receipt['macro_popup_controls']=controls(t);t.persist()
    require(click_case(t,'fixture.cancel_new_macro','Cancel the unchanged new-macro dialog.',
        lambda c:c['text']=='Cancel' and c['name']!='MacroCancelButton',lambda b,a,s:{'status':'macro_popup_closed' if s and
            'MacroPopupFrame' not in a['panels'] and a.get('macros')==[0,0] else 'client_or_protocol_failure'}),'macro_popup_closed')
    t.clean_panels()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    t=Trial(a.output,controller='code')
    try:native_suite(t,operations=recon);t.receipt['completed']=True
    except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
