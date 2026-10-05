"""Inspect owned stock Alchemy controls before testing recipe variants."""
import argparse,json,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_control_target import target
from .interaction_operations import controls,point
from .interaction_macros import require
from .interaction_spellbook_professions import suite as profession_suite
from .interaction_keybindings_native import suite as native_suite


class RecipeTrial(Trial):
    def step(self,case_id,goal,actions,oracle,**kwargs):
        # Retain the requested hold in each case. Background clients can idle
        # near one FPS; each ordinary click must span a full update.
        actions={k:{**v,'hold':max(v.get('hold',0),1.2)} if v['kind']=='click' else v
            for k,v in actions.items()}
        return super().step(case_id,goal,actions,oracle,**kwargs)


def stock_click(t,label,predicate,panel):
    control=target(t,label,predicate)
    if not control.get('enabled') or control['kind'] not in ('Button','CheckButton'):
        raise RuntimeError('stock profession control is not one enabled button')
    t.io.move(*point(control));time.sleep(1)
    require(t.step(label,'Use the observed stock profession control.',
        {'click':{'kind':'click','value':point(control),'hold':1.2}},
        lambda b,a,s:{'status':'owned_profession_panel_pass' if s=='click' and panel in a['panels'] and
            not a.get('lua_errors') and not a.get('blocked_actions') else 'client_or_protocol_failure'},
        diagnostic_action='click',await_state=lambda a:panel in a['panels']),'owned_profession_panel_pass')


def inspect_recipes(t):
    try:
        stock_click(t,'fixture.open_owned_alchemy',lambda c:c['text']=='Alchemy','TradeSkillFrame')
        state,frame=t.observe('stock_alchemy_rendered')
        t.receipt['recipe_recon']={'controls':controls(t),'state':state,'frame':frame,
            'qualification':'Control reconnaissance only. Filters, recipe/reagent tooltips and crafting variants remain open.'}
        t.persist()
        if not state.get('trade_skill') or state['trade_skill'][0]!='Alchemy' or state.get('recipe_count',0)<=0:
            raise RuntimeError('owned Alchemy recipe catalog is absent')
    finally:
        t.clean_panels()
        stock_click(t,'fixture.return_to_profession_book',lambda c:c['name']=='SpellbookMicroButton','SpellBookFrame')


def restore_source(t,source):
    from .interaction_spellbook_navigation import detail
    source=source.resolve()
    if not source.is_relative_to(lab.ROOT/'evidence') or source.name!='episode.json':
        raise ValueError('requires a private failed recipe episode')
    old=json.loads(source.read_text());baseline=old.get('native_baseline')
    if (old.get('completed') or not old.get('finished_at') or old['actor']!=t.fixture or
        old['runtime']!=t.receipt['runtime'] or not old.get('native_resources_preserved') or
        len(old.get('native_restoration',{}).get('checks',{}))!=10 or
        not all(old['native_restoration']['checks'].values()) or baseline!=t.receipt['native_baseline']):
        raise RuntimeError('failed recipe source or restored native baseline differs')
    layout=old['book_layout_baseline'];t.receipt['restore_source']={'path':str(source),'sha256':lab.sha256(source)};t.persist()
    stock_click(t,'fixture.verify_original_recipe_book',lambda c:c['name']=='SpellbookMicroButton','SpellBookFrame')
    current=detail(t,'source_recipe_layout',book_type=layout['book_type'],line=layout['skill_line'],page=layout['page'])
    checks={k:current.get(k)==layout.get(k) for k in ('book_type','skill_line','page','pages')}
    checks['visible']=current['visible'];t.receipt['source_book_restoration']={'checks':checks};t.persist()
    if not all(checks.values()):raise RuntimeError('original failed recipe book layout differs')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--restore-from',type=Path)
    args=parser.parse_args();out=args.output.resolve()
    if not out.is_relative_to(lab.ROOT/'evidence'):parser.error('requires a private owned evidence output')
    with actor('primary'):
        t=RecipeTrial(out,controller='code')
        try:
            if t.fixture['guid']!=1:raise RuntimeError('requires the owned trained primary warrior')
            native_suite(t,operations=lambda t:restore_source(t,args.restore_from) if args.restore_from else
                profession_suite(t,after_tab=inspect_recipes),preserve_settings=False)
            t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:
            t.receipt['finished_at']=time.time();t.persist()
            print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure')}),flush=True)


if __name__=='__main__':main()
