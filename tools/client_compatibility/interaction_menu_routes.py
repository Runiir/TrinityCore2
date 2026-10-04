"""Inspect and close stock game-menu panels without changing their contents."""
import argparse,json,time
from pathlib import Path
from .interaction_trial import Trial
from .interaction_keybindings_native import suite as native_suite
from .interaction_operations import click_case,controls,point
from .interaction_macros import require

ROUTES={'macros':('Macros','MacroFrame'),'addons':('AddOns','AddonList'),
        'help':('Support','HelpFrame')}


def suite(t,route):
    caption,panel=ROUTES[route];t.clean_panels();before,_=t.observe('menu_route_fixture')
    require(t.step('menu.open','Open the game menu.',
        {'menu':{'kind':'key','value':'Escape','hold':.4,'description':'Open the Game Menu.'}},
        lambda b,a,s:{'status':'menu_open_pass' if 'GameMenuFrame' in a['panels'] else
            'client_or_protocol_failure'},diagnostic_action='menu'),'menu_open_pass')
    def opened(b,a,selected):
        rows=controls(t);t.receipt['route_controls']=rows;t.persist()
        visible=panel in a['panels'] or (route=='addons' and any(c['name'].startswith(panel) for c in rows))
        return {'status':'menu_route_open_pass' if selected and visible and not a.get('lua_errors') else
            'client_or_protocol_failure','oracle':{'panel':panel,'visible':visible}}
    require(click_case(t,'menu.'+route,'Open the stock '+caption+' panel.',
        lambda c:c['text']==caption,opened),'menu_route_open_pass')
    t.observe('menu_route_rendered')
    def closed(b,a,selected):
        rows=controls(t);remaining=[c for c in rows if c['name'].startswith(panel)]
        return {'status':'menu_route_close_pass' if panel not in a['panels'] and not remaining and
            a.get('macros')==before.get('macros') and not a.get('lua_errors') else
            'client_or_protocol_failure','oracle':{'remaining_panel_controls':remaining,
            'macro_counts_preserved':a.get('macros')==before.get('macros')}}
    if route=='help':
        rows=controls(t);buttons=[c for c in rows if c['kind']=='Button' and c['enabled'] and
            not c['name'] and not c['text']]
        if len(buttons)!=1:raise RuntimeError('one observed stock Support close button is required')
        button=buttons[0];t.receipt['support_close_control']=button;t.persist()
        require(click_case(t,'help.close','Click the observed stock Support close button.',
            lambda c:c['kind']=='Button' and not c['name'] and not c['text'] and point(c)==point(button),
            closed,await_state=lambda s:panel not in s['panels']),'menu_route_close_pass')
    else:
        require(t.step(route+'.close','Close this panel with Escape.',
            {'close':{'kind':'key','value':'Escape','hold':.4,'description':'Close the inspected stock panel.'}},
            closed,diagnostic_action='close'),'menu_route_close_pass')
    t.clean_panels()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--route',choices=ROUTES,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();t=Trial(a.output,controller='code')
    try:native_suite(t,lambda trial:suite(trial,a.route));t.receipt['completed']=True
    except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
