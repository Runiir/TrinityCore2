"""Test stock Alchemy makeable filtering and native product/reagent item tooltips."""
import argparse,json,re,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_profession_recipes import RecipeTrial,stock_click
from .interaction_control_target import target,edit
from .interaction_operations import point
from .interaction_macros import require
from .interaction_tooltips import items,tooltip
from .interaction_spellbook_professions import suite as profession_suite,skills
from .interaction_keybindings_native import suite as native_suite
from .interaction_spellbook_recon import resources
from .interaction_spellbook_navigation import known
from .observation.inventory import Inventory

FILTER='TradeSkillFrameAvailableFilterCheckButton'
NAME='Potion of Deepholm';SPELL=80725;PRODUCT=58487;REAGENTS={52986:5,3371:1}


def item_id(link):
    match=re.search(r'\|Hitem:(\d+)',link or '')
    return int(match[1]) if match else None


def native_preserved(t,oracle):
    return (resources(oracle)==t.receipt['baseline'] and
        known(t.fixture['guid'])==t.receipt['native_persisted_spells'] and
        skills(t.fixture['guid'])==t.receipt['native_skills'])


def filter_click(t,wanted,baseline,oracle,label):
    control=target(t,label,lambda c:c['name']==FILTER)
    if control['kind']!='CheckButton' or not control.get('enabled') or control.get('checked')==wanted:
        raise RuntimeError('requires the observed opposite makeable checkbox state')
    t.io.move(*point(control));time.sleep(1)
    expected=0 if wanted else baseline['recipe_count']
    def outcome(b,a,s):
        current=target(t,label+'_checked',lambda c:c['name']==FILTER)
        checks={'ordinary_click':s=='click','checked':current.get('checked')==wanted,
            'expected_recipe_count':a.get('recipe_count')==expected,
            'profession_unchanged':a.get('trade_skill')==baseline['trade_skill'],
            'native_preserved':native_preserved(t,oracle),
            'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        return {'status':'recipe_filter_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'expected_checked':wanted,'expected_count':expected,'control':current}}
    require(t.step(label,'Toggle the observed Have Materials recipe filter.',
        {'click':{'kind':'click','value':point(control),'hold':1.2}},outcome,diagnostic_action='click',
        await_state=lambda a:a.get('recipe_count')==expected),'recipe_filter_pass')


def hover_item(t,oracle,control_name,entry,title,label):
    control=target(t,label,lambda c:c['name']==control_name)
    if control['kind']!='Button' or not control.get('enabled'):
        raise RuntimeError('requires the observed stock recipe item button')
    def outcome(b,a,s):
        probe=tooltip(t,label.replace('.','_'));lines=probe.get('lines') or []
        first=re.sub(r'\|c[0-9a-fA-F]{8}|\|r','',lines[0].get('left','')) if lines else ''
        checks={'ordinary_hover':s=='hover','visible':probe.get('visible'),
            'owner':probe.get('owner')==control_name,'native_item_identity':item_id(probe.get('item_link'))==entry,
            'native_item_name':probe.get('item_name')==title,'rendered_title':first==title,
            'recipe_unchanged':a.get('selected_recipe',{}).get('recipe_link')==t.recipe_before['selected_recipe']['recipe_link'],
            'native_preserved':native_preserved(t,oracle),
            'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        return {'status':'recipe_item_tooltip_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'expected_item':entry,'expected_title':title,'public':probe}}
    require(t.step(label,'Hover the stock '+title+' recipe item.',
        {'hover':{'kind':'hover','value':point(control)}},outcome,diagnostic_action='hover'),'recipe_item_tooltip_pass')


def restore_selection(t,baseline):
    state,_=t.observe('recipe_selection_restore_before')
    if state.get('selected_recipe')!=baseline.get('selected_recipe'):
        require(edit(t,'fixture.search_original_recipe','Find the original selected recipe.',
            lambda c:c['name']=='TradeSkillFrameEditBox',NAME),'ui_edit_pass')
        row=target(t,'fixture.select_original_recipe',lambda c:c['name'].startswith('TradeSkillSkill') and c['text'].strip()==NAME)
        require(t.step('fixture.select_original_recipe','Select the original Potion of Deepholm recipe.',
            {'click':{'kind':'click','value':point(row),'hold':1.2}},
            lambda b,a,s:{'status':'recipe_selection_restored' if s=='click' and
                a.get('selected_recipe')==baseline['selected_recipe'] else 'client_or_protocol_failure'},
            diagnostic_action='click',await_state=lambda a:a.get('selected_recipe')==baseline['selected_recipe']),
            'recipe_selection_restored')
    search=target(t,'fixture.recipe_search_restore_guard',lambda c:c['name']=='TradeSkillFrameEditBox')
    if search['text']!='Search':
        require(edit(t,'fixture.clear_recipe_restore_search','Restore the unfiltered recipe search.',
            lambda c:c['name']=='TradeSkillFrameEditBox',''),'ui_edit_pass')
        t.execute({'kind':'key','value':'Return','hold':1.2})
    state,frame=t.observe('recipe_layout_restored')
    current=target(t,'recipe_filter_restored',lambda c:c['name']==FILTER)
    search=target(t,'recipe_search_restored',lambda c:c['name']=='TradeSkillFrameEditBox')
    checks={k:state.get(k)==baseline.get(k) for k in ('trade_skill','recipe_count','recipe_selection','selected_recipe','recipe_reagents')}
    checks.update(filter_unchecked=current.get('checked') is False,search=search['text']=='Search')
    t.receipt['recipe_layout_restoration']={'checks':checks,'frame':frame};t.persist()
    if not all(checks.values()):raise RuntimeError('original recipe layout differs')


def variants(t):
    oracle=Inventory(lab.ROOT,actors.session_entry(t.fixture)['session'],t.fixture['guid']).poll()
    baseline=None
    try:
        stock_click(t,'fixture.open_owned_alchemy',lambda c:c['text']=='Alchemy','TradeSkillFrame')
        baseline,frame=t.observe('recipe_variant_baseline');t.recipe_before=baseline
        selected=baseline.get('selected_recipe',{});reagents=baseline.get('recipe_reagents') or []
        catalogs,digest=items([PRODUCT,*REAGENTS]);control=target(t,'recipe_original_filter',lambda c:c['name']==FILTER)
        search=target(t,'recipe_original_search',lambda c:c['name']=='TradeSkillFrameEditBox')
        checks={'observer105':baseline.get('observer_version')==105,'alchemy':baseline.get('trade_skill')==['Alchemy',525,525],
            'unfiltered':control.get('checked') is False and search['text']=='Search','catalog':baseline.get('recipe_count',0)>0,
            'native_known_recipe':SPELL in t.receipt['native_known_spell_packet']['ids'],
            'recipe_identity':selected.get('name')==NAME and item_id(selected.get('link'))==PRODUCT and
                re.search(r'\|Henchant:80725\|',selected.get('recipe_link','')) is not None,
            'native_reagents':{item_id(r.get('link')):r['need'] for r in reagents}==REAGENTS,
            'zero_reagents':len(reagents)==2 and all(r.get('have')==oracle.count(item_id(r.get('link')))==0 for r in reagents),
            'native_names':all(catalogs[item_id(r['link'])]['name']==r['name'] for r in reagents)}
        t.receipt['recipe_variant_contract']={'checks':checks,'baseline':baseline,'frame':frame,
            'native_items':catalogs,'native_item_catalog_sha256':digest,
            'scope':'Unfiltered owned Alchemy; zero-material makeable filter; Deepholm result and its two reagent item tooltips. No crafting.'};t.persist()
        if not all(checks.values()):raise RuntimeError('native recipe variant fixture differs')
        hover_item(t,oracle,'TradeSkillSkillIcon',PRODUCT,catalogs[PRODUCT]['name'],'professions.recipe_tooltip')
        for number,entry in enumerate(REAGENTS,1):
            hover_item(t,oracle,'TradeSkillReagent'+str(number),entry,catalogs[entry]['name'],
                'professions.reagent_tooltip.'+str(entry))
        filter_click(t,True,baseline,oracle,'professions.recipe_filter.makeable_on')
        filter_click(t,False,baseline,oracle,'professions.recipe_filter.makeable_off')
        restore_selection(t,baseline)
    finally:
        state,_=t.observe('recipe_variant_cleanup_guard')
        if 'TradeSkillFrame' in state['panels']:
            if baseline is not None and all(t.receipt.get('recipe_variant_contract',{}).get('checks',{}).values()):
                current=target(t,'fixture.recipe_filter_cleanup_guard',lambda c:c['name']==FILTER)
                if current.get('checked'):filter_click(t,False,baseline,oracle,'fixture.restore_recipe_filter')
                if not all(t.receipt.get('recipe_layout_restoration',{}).get('checks',{'missing':False}).values()):
                    restore_selection(t,baseline)
            close=target(t,'fixture.close_recipe_variants',lambda c:c['name']=='TradeSkillCancelButton' and c['text']=='Exit')
            t.io.move(*point(close));time.sleep(1)
            require(t.step('fixture.close_recipe_variants','Close stock Alchemy with Exit.',
                {'click':{'kind':'click','value':point(close),'hold':1.2}},
                lambda b,a,s:{'status':'recipe_panel_closed' if s=='click' and 'TradeSkillFrame' not in a['panels'] else
                    'client_or_protocol_failure'},diagnostic_action='click',await_state=lambda a:'TradeSkillFrame' not in a['panels']),
                'recipe_panel_closed')
        state,_=t.observe('recipe_variant_book_guard')
        if 'SpellBookFrame' not in state['panels']:
            stock_click(t,'fixture.return_to_profession_book',lambda c:c['name']=='SpellbookMicroButton','SpellBookFrame')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if not a.output.resolve().is_relative_to(lab.ROOT/'evidence'):p.error('requires private evidence output')
    with actor('primary'):
        t=RecipeTrial(a.output,controller='code')
        try:
            native_suite(t,operations=lambda t:profession_suite(t,after_tab=variants),preserve_settings=False)
            t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:
            t.receipt['finished_at']=time.time();t.persist();print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure')}),flush=True)


if __name__=='__main__':main()
