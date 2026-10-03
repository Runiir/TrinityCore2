"""Inspect stock settings search through ordinary owned inputs and restore it."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_operations import controls,click_case,point
from .interaction_macros import edit_case,require
from .observation.inventory import Inventory


def resources(oracle):
    oracle.poll()
    return {'money':oracle.money(),'equipment':[oracle.equipment(i) for i in range(1,20)]}


def open_search(t):
    require(t.step('settings.inspect_menu','Open the game menu.',
        {'open':{'kind':'key','value':'Escape','description':'Open the ordinary game menu.'}},
        lambda b,a,s:{'status':'panel_open_pass' if 'GameMenuFrame' in a['panels'] else 'client_or_protocol_failure'},
        diagnostic_action='open',await_state=lambda a:'GameMenuFrame' in a['panels']),'panel_open_pass')
    require(click_case(t,'settings.inspect_open','Open stock settings.',lambda c:c['text']=='Options',
        lambda b,a,s:{'status':'panel_open_pass' if s and 'SettingsPanel' in a['panels'] else 'client_or_protocol_failure'},
        await_state=lambda a:'SettingsPanel' in a['panels']),'panel_open_pass')
    fields=[c for c in controls(t) if c['kind']=='EditBox' and c['enabled']]
    if len(fields)!=1:raise RuntimeError('require one visible stock settings search field')
    field=fields[0];t.receipt['search_field']=field;t.persist();return field


def suite(t):
    session=actors.session_entry(t.fixture)['session'];oracle=Inventory(lab.ROOT,session,t.fixture['guid']).poll()
    t.clean_panels();before=resources(oracle);t.receipt['baseline']=before;t.persist();original=None
    try:
        field=open_search(t);original=field['text']
        predicate=lambda c:c['kind']=='EditBox' and point(c)==point(field)
        for term in ['helm','cloak']:
            require(edit_case(t,'settings.search.'+term,'Search stock settings for '+term+'.',predicate,term),'ui_edit_pass')
            rows=controls(t);state,frame=t.observe('search_'+term)
            t.receipt.setdefault('search_results',{})[term]={'controls':rows,'state':state,'frame':frame};t.persist()
    finally:
        try:
            if original is not None:
                require(edit_case(t,'settings.search.restore','Restore the original settings search.',predicate,original),'ui_edit_pass')
                require(click_case(t,'settings.inspect_close','Close the stock settings window.',lambda c:c['text']=='Close',
                    lambda b,a,s:{'status':'panel_closed_pass' if s and 'SettingsPanel' not in a['panels'] else 'client_or_protocol_failure'},
                    await_state=lambda a:'SettingsPanel' not in a['panels']),'panel_closed_pass')
            t.clean_panels()
        finally:
            t.receipt['native_after']=resources(oracle);t.receipt['native_resources_preserved']=t.receipt['native_after']==before;t.persist()
            if not t.receipt['native_resources_preserved']:raise RuntimeError('settings inspection changed native equipment or money')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();t=Trial(a.output,controller='code')
    try:suite(t);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
