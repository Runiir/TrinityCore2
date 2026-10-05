"""Close the exact owned Alchemy fixture when the broad state page is unavailable."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_profession_recipes import RecipeTrial,restore_source
from .interaction_social import actor
from .interaction_control_target import target
from .interaction_operations import point
from .interaction_observation import read_current_page
from .interaction_spellbook_recon import resources
from .interaction_spellbook_navigation import known
from .interaction_stance_bar import native_state,restored_native_state
from .interaction_spellbook_actions import saved_actions
from .interaction_actionbar_pages import detail as bar_detail
from .interaction_sit_stand import pose,afk
from .interaction_keybindings_native import suite as native_suite
from .interaction_ground_movement import position
from .interaction_trial import binding_key
from .observation.inventory import Inventory


def recover(t,failed,baseline):
    sources=[]
    for path in (failed,baseline):
        path=path.resolve()
        if path.name!='episode.json' or not path.is_relative_to(lab.ROOT/'evidence'):
            raise ValueError('requires private owned recipe episodes')
        value=json.loads(path.read_text())
        if (value.get('completed') or not value.get('finished_at') or value['actor']!=t.fixture or
            value['runtime']!=t.receipt['runtime'] or not value.get('native_resources_preserved')):
            raise RuntimeError('closed failed recipe source differs')
        sources.append(value)
    failed_value,old=sources;expected=old['native_baseline'];checks=old['native_restoration']['checks']
    if len(checks)!=10 or not all(checks.values()) or failed_value['native_baseline']!=expected:
        raise RuntimeError('recipe sources do not share the restored original baseline')
    session=actors.session_entry(t.fixture)['session'];oracle=Inventory(lab.ROOT,session,t.fixture['guid']).poll()
    current={'resources':resources(oracle),'stats':native_state(oracle),'spells':known(t.fixture['guid']),
        'actions':saved_actions(t.fixture['guid']),'position':position(t.fixture['guid'])}
    native_checks={key:current[key]==expected[key] for key in current if key!='stats'}
    native_checks['stats']=restored_native_state(expected['stats'],current['stats'])
    t.receipt['failed_recipe_recovery']={'sources':[{'path':str(p.resolve()),'sha256':lab.sha256(p)} for p in (failed,baseline)],
        'native_checks_before':native_checks,'scope':'Source-bound fixture cleanup only; no operation qualification.'};t.persist()
    if not all(native_checks.values()):raise RuntimeError('native recipe resources changed before recovery')
    public,frame=read_current_page(t,'failed_recipe_controls_guard','controls')
    if ('TradeSkillFrame' not in public['panels'] or
        not set(public['panels']).issubset({'TradeSkillFrame','SpellBookFrame'}) or public.get('chat_edit_open')):
        raise RuntimeError('requires only the owned Alchemy/book panels and closed chat')
    control=target(t,'fixture.close_failed_alchemy',lambda c:c['name']=='TradeSkillCancelButton' and c['text']=='Exit')
    if control['kind']!='Button' or not control.get('enabled'):raise RuntimeError('owned Alchemy Exit is not enabled')
    t.receipt['failed_recipe_recovery']['ordinary_close']={'control':control,'frame':frame,'point':point(control),'hold':1.2};t.persist()
    t.io.move(*point(control));time.sleep(1);t.io.click(*point(control),hold=1.2)
    closed,closed_frame=t.observe('failed_alchemy_closed',seconds=60)
    t.receipt['failed_recipe_recovery']['closed_frame']=closed_frame;t.persist()
    if 'TradeSkillFrame' in closed['panels']:raise RuntimeError('owned Alchemy close did not settle; no replay')
    t.clean_panels()
    if afk(oracle)!=expected['afk']:t.execute({'kind':'chat','value':'/afk'})
    if pose(oracle)!=expected['pose']:
        if {pose(oracle)['stand'],expected['pose']['stand']}!={0,1}:raise RuntimeError('unsupported original pose')
        bar=bar_detail(t,'source_recipe_pose_binding')
        t.execute({'kind':'key','value':binding_key(bar['keys']['SITORSTAND'][0]),'hold':1.2});time.sleep(12)
    native_suite(t,operations=lambda t:restore_source(t,baseline),preserve_settings=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('failed','baseline','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    if not args.output.resolve().is_relative_to(lab.ROOT/'evidence'):parser.error('requires private evidence output')
    with actor('primary'):
        t=RecipeTrial(args.output,controller='code')
        try:recover(t,args.failed,args.baseline);t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure')}),flush=True)


if __name__=='__main__':main()
