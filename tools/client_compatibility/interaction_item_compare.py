"""Compare an owned backpack sword with the equipped sword using normal Shift."""
import argparse,json,re,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_operations import command,point
from .interaction_inventory_moves import slot_control
from .interaction_weapon_swap import open_fixture
from .interaction_equipment_set_roundtrip import stable
from .interaction_tooltips import baseline,items
from .interaction_observation import read_page,read_current_page
from .observation.inventory import Inventory
from .interaction_control_target import target
from .interaction_keybindings_native import suite as native_suite
from .interaction_macros import require


def identity(tip):
    match=re.search(r'\|Hitem:(\d+)',tip.get('item_link') or '')
    return int(match[1]) if match else None


def suite(t,bag_contracts=False):
    if t.fixture['guid']!=1:raise RuntimeError('requires the owned geared primary warrior')
    session=actors.session_entry(t.fixture)['session'];oracle=Inventory(lab.ROOT,session,1).poll()
    original=stable(baseline());worn=oracle.equipment(16);stored=oracle.slot(0,10)
    catalog,digest=items([worn['id'],stored['id']])
    if (worn['id']!=78478 or stored['id']!=49778 or oracle.equipment(17)['guid'] or
        not all(row['inventory_type']==17 for row in catalog.values())):
        raise RuntimeError('requires the exact owned two-hand sword comparison fixture')
    t.receipt.update(baseline=original,native_session=session,fixture={'worn':worn,'stored':stored,
        'catalog':catalog,'catalog_sha256':digest});t.persist();selected=False
    try:
        t.clean_panels();state,_=t.observe('compare_before')
        if state.get('observer_version',0)<56:raise RuntimeError('requires read-only comparison observer v56')
        open_fixture(t)
        control=target(t,'owned_comparison_sword',lambda c:c['kind']=='Button' and
            c.get('bag_id')==0 and c.get('bag_slot')==10) if bag_contracts else slot_control(t,0,10)
        if control is None:raise RuntimeError('owned backpack sword control is absent')
        state,frame=read_page(t,'comparison_page','tooltip','/tcui tooltip');selected=True
        if state['tooltip_probe']['shift_down']:raise RuntimeError('private Shift is already held')
        if bag_contracts:
            def hover_outcome(b,a,s):
                state,frame=read_current_page(t,'bag_item_tooltip','tooltip',lambda a:
                    a['tooltip_probe']['visible'] and identity(a['tooltip_probe'])==stored['id'])
                probe=state['tooltip_probe']
                checks={'ordinary_hover':s=='hover','visible':probe['visible'],
                    'backpack_identity':identity(probe)==stored['id'],
                    'native_catalog_name':probe.get('item_name')==catalog[stored['id']]['name'],
                    'owner':probe.get('owner')==control['name'],'without_shift':not probe['shift_down'],
                    'complete_native_fixture':stable(baseline())==original,
                    'clean':not state.get('lua_errors') and not state.get('blocked_actions')}
                return {'status':'stock_bag_tooltip_pass' if all(checks.values()) else 'client_or_protocol_failure',
                    'oracle':{'checks':checks,'public':probe,'frame':frame}}
            require(t.step('bags.item_tooltip','Inspect the owned backpack sword with an ordinary hover.',
                {'hover':{'kind':'hover','value':point(control),'description':'Hover the observed backpack sword.'}},
                hover_outcome,diagnostic_action='hover'),'stock_bag_tooltip_pass')
        case={'id':'bags.compare_tooltip' if bag_contracts else 'character.compare_items','time':time.time(),'status':'started',
            'goal':'Compare the owned backpack sword to the currently equipped sword.',
            'selected':'shift_hover','ordinary_input':{'modifier':'shift','hover':point(control)}}
        t.receipt['cases'].append(case);t.persist()
        with t.io.hold_modifier('shift'):
            t.io.move(*point(control));time.sleep(.8)
            state,frame=read_current_page(t,'item_comparison','tooltip',lambda a:
                a['tooltip_probe']['shift_down'] and a['tooltip_probe']['visible'] and
                any(x['visible'] for x in a['tooltip_probe']['comparisons']))
        probe=state['tooltip_probe'];comparisons=[x for x in probe['comparisons'] if x['visible']]
        checks={'normal_private_shift':probe['shift_down'],
            'backpack_identity':identity(probe)==stored['id'] and probe.get('item_name')==catalog[stored['id']]['name'],
            'equipped_comparison_identity':len(comparisons)==1 and identity(comparisons[0])==worn['id'] and
                comparisons[0].get('item_name')==catalog[worn['id']]['name'],
            'complete_native_fixture':stable(baseline())==original,
            'ui_clean':not state.get('lua_errors') and not state.get('blocked_actions')}
        case.update(status='stock_item_comparison_pass' if all(checks.values()) else 'client_or_protocol_failure',
            oracle={'checks':checks,'public':probe},frame=frame,modifier_released=True);t.persist()
        if not all(checks.values()):raise RuntimeError('stock comparison identities or native fixture differ')
        after,after_frame=read_current_page(t,'comparison_released','tooltip',lambda a:
            not a['tooltip_probe']['shift_down'] and (a['tooltip_probe']['always_compare'] or
                not any(x['visible'] for x in a['tooltip_probe']['comparisons'])))
        t.receipt['comparison_released']={'public':after['tooltip_probe'],'frame':after_frame};t.persist()
    finally:
        try:
            if selected:command(t,'/tcui state')
            t.clean_panels()
        finally:
            t.receipt['native_after']=stable(baseline());t.receipt['native_resources_preserved']=t.receipt['native_after']==original;t.persist()
    if not t.receipt['native_resources_preserved']:raise RuntimeError('comparison changed the native fixture')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--bag-contracts',action='store_true')
    a=p.parse_args();t=Trial(a.output,controller='code')
    try:
        if a.bag_contracts:native_suite(t,operations=lambda t:suite(t,bag_contracts=True),preserve_settings=False)
        else:suite(t)
        t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
