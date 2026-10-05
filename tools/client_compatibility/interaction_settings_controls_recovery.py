"""Recover the exact closed Interact proxy restoration failure with ordinary inputs."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_settings_volume import SettingsTrial,restore_layout,layout_checks,click_control
from .interaction_settings_controls import interact_fixture_restorable,restore_interact_fixture
from .interaction_settings_booleans import detail
from .interaction_settings_search import open_search
from .interaction_control_target import target
from .interaction_spellbook_recon import resources
from .interaction_stance_bar import native_state,restored_native_state
from .interaction_spellbook_navigation import known
from .interaction_spellbook_actions import saved_actions
from .interaction_sit_stand import pose,afk
from .interaction_ground_movement import position
from .observation.inventory import Inventory


def source_layout(old,fixture,runtime):
    expected={k:'stock_control_setting_pass' for k in ('settings.interface.change','settings.interface.restore',
        'settings.keyboard_controls.change','settings.keyboard_controls.restore')}
    passed={c['id']:c['status'] for c in old.get('cases',[])}
    layout=old.get('control_layout_baseline',{})
    last=old.get('settings_details',{}).get('fixture.restore_stock_controls_restored',{}).get('state',{}).get('settings_probe',{})
    if (old.get('completed') or not old.get('finished_at') or old.get('failure')!=
        'RuntimeError: panel cleanup did not change state; refusing to replay Escape' or
        old.get('actor')!=fixture or old.get('runtime')!=runtime or old.get('code_commit')!=
        '5806289004811953b1c0fe829a03c06237c5cd1c' or
        any(passed.get(k)!=v for k,v in expected.items()) or
        old.get('volume_layout_restoration',{}).get('checks')!=
        {'search':True,'category':True,'values':True,'unapplied':True,'cvars':False} or
        not interact_fixture_restorable(last,layout)):
        raise RuntimeError('exact closed Interact proxy failure or owned runtime differs')
    return layout


def verify_resume(old,source,fixture,runtime):
    cases=old.get('cases',[])
    if (old.get('completed') or not old.get('finished_at') or old.get('failure')!=
        'RuntimeError: operation did not advance: settings.inspect_menu client_or_protocol_failure' or
        old.get('actor')!=fixture or old.get('runtime')!=runtime or old.get('source')!=source or
        [(c.get('id'),c.get('status')) for c in cases]!=[
            ('fixture.recover_interact_none_close','settings_panel_closed'),
            ('fixture.recover_interact_none_console','fixture_console_submitted'),
            ('settings.inspect_menu','client_or_protocol_failure')] or
        cases[-1].get('after',{}).get('panels') or cases[-1].get('after',{}).get('chat_edit_open') or
        not all(old.get('source_preflight',{}).get('native',{}).values()) or
        len(old.get('source_preflight',{}).get('native',{}))!=10):
        raise RuntimeError('exact closed post-console menu failure differs')


def recover(t,path,resume_from=None,close_only=False,closed_fixture_from=None):
    path=path.resolve()
    if path.name!='episode.json' or not path.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('requires a private closed Interact proxy failure')
    old=json.loads(path.read_text());layout=source_layout(old,t.fixture,t.receipt['runtime'])
    base=old['native_baseline'];before=old['cases'][0]['before']
    oracle=Inventory(lab.ROOT,actors.session_entry(t.fixture)['session'],t.fixture['guid']).poll()
    t.receipt.update(source={'path':str(path),'sha256':lab.sha256(path)},qualified_scope=
        'Source-bound cleanup only. Verify the exact stock proxy 0-to-1 difference and native fixture, restore None=0 with a fixed ordinary chat SetCVar fixture script, then verify and close the stock Settings panel. No gameplay qualification.');t.persist()
    def native_checks(state):
        return {'resources':resources(oracle)==base['resources'],
            'stats':restored_native_state(base['stats'],native_state(oracle)),
            'spells':known(t.fixture['guid'])==base['spells'],'actions':saved_actions(t.fixture['guid'])==base['actions'],
            'pose':pose(oracle)==base['pose'],'afk':afk(oracle)==base['afk'],
            'position':position(t.fixture['guid'])==base['position'] and state['world_position']==before['world_position'],
            'group':state['group']==before['group'],'no_lua_errors':not state.get('lua_errors'),
            'no_blocked_actions':not state.get('blocked_actions')}
    state,frame=t.observe('source_control_panel');checks=native_checks(state)
    if closed_fixture_from is not None:
        closed_fixture_from=closed_fixture_from.resolve()
        if closed_fixture_from.name!='episode.json' or not closed_fixture_from.is_relative_to(lab.ROOT/'evidence'):
            raise ValueError('requires a private close-only source')
        prior=json.loads(closed_fixture_from.read_text())
        if (prior.get('actor')!=t.fixture or prior.get('runtime')!=t.receipt['runtime'] or
            prior.get('source')!=t.receipt['source'] or prior.get('completed') is not True or not prior.get('finished_at') or
            prior.get('unrestored_cvars')!={'softTargetInteract':{'original':'0','after':'1'}} or
            len(prior.get('source_restoration',{}).get('checks',{}))!=11 or
            not all(prior['source_restoration']['checks'].values()) or not all(checks.values()) or
            state.get('panels') or state.get('chat_edit_open')):
            raise RuntimeError('verified closed Interact fixture or native baseline differs')
        t.receipt['closed_fixture_source']={'path':str(closed_fixture_from),'sha256':lab.sha256(closed_fixture_from)};t.persist()
        t.settings_search=open_search(t)
    if resume_from is not None:
        resume_from=resume_from.resolve()
        if resume_from.name!='episode.json' or not resume_from.is_relative_to(lab.ROOT/'evidence'):
            raise ValueError('requires a private closed post-console failure')
        verify_resume(json.loads(resume_from.read_text()),t.receipt['source'],t.fixture,t.receipt['runtime'])
        t.receipt['resume_source']={'path':str(resume_from),'sha256':lab.sha256(resume_from)};t.persist()
        if not all(checks.values()) or state.get('panels') or state.get('chat_edit_open'):
            raise RuntimeError('post-console world fixture differs; refusing new input')
        t.settings_search=open_search(t);current=detail(t,'source_console_setting_verified')
        settings=layout_checks(current,layout)
        settings.update(interact_binding=current['interact_keys']==layout['interact_keys'],
            move_pad=current['move_pad_visible']==layout['move_pad_visible'])
        t.receipt['source_preflight']={'native':checks,'settings':settings,'frame':frame};t.persist()
        if not all(settings.values()):raise RuntimeError('post-console exact original settings differ')
    else:
        current=detail(t,'source_control_settings')
        settings=interact_fixture_restorable(current,layout) and all(current.get(k)==layout.get(k) for k in ('search','category'))
        t.receipt['source_preflight']={'native':checks,'exact_proxy_difference':settings,'frame':frame};t.persist()
        if not all(checks.values()) or not settings or not current.get('visible') or current.get('unapplied'):
            raise RuntimeError('source native fixture or exact stock proxy difference no longer matches')
        if close_only:
            t.receipt['qualified_scope']='Source-bound close-only cleanup. Original softTargetInteract=0 remains unrestored at stock-disabled1. Other settings and native fixture are verified; no gameplay qualification.'
            t.receipt['unrestored_cvars']={'softTargetInteract':{'original':'0','after':'1'}};t.persist()
            close=target(t,'fixture.close_known_control_panel',lambda c:c['kind']=='Button' and c['text']=='Close')
            click_control(t,'fixture.close_known_control_panel',close,lambda a:'SettingsPanel' not in a['panels'],'settings_panel_closed')
        else:current=restore_interact_fixture(t,layout,current,'fixture.recover_interact_none')
    if not close_only and current['visible']:restore_layout(t,layout,'fixture.recover_control_layout')
    t.clean_panels()
    if afk(oracle)!=base['afk']:t.execute({'kind':'chat','value':'/afk'})
    state,frame=t.observe('source_controls_restored');checks=native_checks(state)
    checks['closed_ui']=not state.get('panels')
    t.receipt['source_restoration']={'checks':checks,'frame':frame};t.persist()
    if not all(checks.values()):raise RuntimeError('source control fixture restoration differs')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--resume-from',type=Path)
    p.add_argument('--close-only',action='store_true');p.add_argument('--closed-fixture-from',type=Path);a=p.parse_args()
    if sum(bool(x) for x in (a.resume_from,a.close_only,a.closed_fixture_from))>1:p.error('choose one recovery entry stage')
    if not a.output.resolve().is_relative_to(lab.ROOT/'evidence'):p.error('requires private evidence output')
    with actor('primary'):
        t=SettingsTrial(a.output,controller='code')
        try:recover(t,a.source,a.resume_from,a.close_only,a.closed_fixture_from);t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:
            t.receipt['finished_at']=time.time();t.persist();print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure')}),flush=True)


if __name__=='__main__':main()
