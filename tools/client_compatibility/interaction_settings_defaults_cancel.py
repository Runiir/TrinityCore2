"""Cancel stock category-default dialogs and verify all observed bindings."""
import argparse,json,math,time
from pathlib import Path
from .interaction_trial import Trial
from .interaction_keybindings_native import suite as native_suite
from .interaction_operations import click_case,command
from .interaction_macros import require,edit_case
from .interaction_settings_search import open_search
from .interaction_settings_booleans import detail
from .interaction_observation import read_page


def catalog(t,label):
    rows=[];pages=[];page=1;total=None
    try:
        while total is None or page<=math.ceil(total/12):
            state,frame=read_page(t,f'{label}_{page:02}','bindings','/tcui bindings '+str(page),
                lambda s:s.get('page')==page)
            total=state['binding_count'];rows.extend(state['rows']);pages.append({'frame':frame,'state':state});page+=1
        if len(rows)!=total or [r['i'] for r in rows]!=list(range(1,total+1)):
            raise RuntimeError('incomplete owned binding catalog')
        t.receipt.setdefault('binding_catalogs',{})[label]={'rows':rows,'pages':pages};t.persist();return rows
    finally:command(t,'/tcui state')


def suite(t):
    original=catalog(t,'all_bindings_before');t.clean_panels();field=open_search(t)
    require(edit_case(t,'fixture.defaults_clear_search','Clear the search before inspecting category defaults.',
        lambda c:c['kind']=='EditBox' and not c['name'],'') ,'ui_edit_pass')
    for category,operation in [('Controls','settings.defaults_cancel'),('Keybindings','keybindings.defaults_cancel')]:
        require(click_case(t,'fixture.defaults_category.'+category,'Select the stock '+category+' category.',
            lambda c:c['text']==category or c['text'].startswith(category+'|T'),
            lambda b,a,s:{'status':'category_pass' if s and
                detail(t,'defaults_category_'+category)['category']['name'].startswith(category) else
                'client_or_protocol_failure'}),'category_pass')
        before=detail(t,'defaults_before_'+category)
        require(click_case(t,operation+'.open','Open the stock Defaults confirmation.',lambda c:c['text']=='Defaults',
            lambda b,a,s:{'status':'defaults_dialog_pass' if s and any(p.startswith('StaticPopup') for p in a['panels'])
                else 'client_or_protocol_failure'}),'defaults_dialog_pass')
        require(click_case(t,operation,'Cancel the Defaults confirmation.',lambda c:c['text']=='Cancel',
            lambda b,a,s:{'status':'defaults_cancel_pass' if s and not any(p.startswith('StaticPopup') for p in a['panels'])
                and 'SettingsPanel' in a['panels'] and detail(t,'defaults_after_'+category)==before else
                'client_or_protocol_failure'}),'defaults_cancel_pass')
    require(click_case(t,'fixture.defaults_close','Close the unchanged settings.',lambda c:c['text']=='Close',
        lambda b,a,s:{'status':'settings_closed_pass' if s and 'SettingsPanel' not in a['panels'] else
            'client_or_protocol_failure'}),'settings_closed_pass')
    after=catalog(t,'all_bindings_after');t.receipt['all_bindings_preserved']=after==original;t.persist()
    if after!=original:raise RuntimeError('default cancellation changed the observed binding catalog')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    t=Trial(a.output,controller='code')
    try:native_suite(t,suite);t.receipt['completed']=True
    except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
