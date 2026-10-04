"""Toggle stock Action Bar2, verify its native mask and visible grid, then restore."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_settings_search import open_search
from .interaction_settings_booleans import detail as settings,search,toggle
from .interaction_actionbar_pages import detail as bars
from .interaction_operations import controls,point,click_case
from .interaction_macros import require
from .interaction_spellbook_navigation import known
from .interaction_spellbook_actions import saved_actions
from .interaction_spellbook_recon import resources
from .observation.inventory import Inventory
from .observation.journal import entries
from .world.objects import INDEX

VARIABLE='PROXY_SHOW_ACTIONBAR_2'


def mask(oracle):
    oracle.poll();return (oracle.objects[oracle.guid].get(INDEX['PLAYER_FIELD_BYTES'],0)>>16)&255


def signature(probe):return [(r['slot'],r.get('kind'),r.get('id')) for r in probe['actions']]


def toggle_extra(t,oracle,wanted,label):
    candidates=[c for c in controls(t) if c['kind']=='CheckButton' and
        c.get('setting_variable')==VARIABLE and c['enabled']]
    if len(candidates)!=1:raise RuntimeError('requires one observed Action Bar2 checkbox')
    button=candidates[0];since=time.time();expected=t.mask_baseline|(1 if wanted else 0)
    def outcome(b,a,s):
        value=settings(t,label+'_value',lambda p:p['values'].get(VARIABLE) is wanted)
        packets=[{'time':r['time'],'body':r['body']} for r in entries(lab.ROOT/'evidence/world_packets.jsonl')
            if r.get('session')==t.session and r.get('time',0)>=since and r.get('direction')=='to_native' and
            r.get('name') in ['CMSG_SET_ACTION_BAR_TOGGLES','CMSG_SET_ACTIONBAR_TOGGLES'] and
            bytes.fromhex(r.get('body',''))==bytes([expected])]
        actual=mask(oracle)
        checks={'ordinary_checkbox':bool(s),'public_setting':value['values'].get(VARIABLE) is wanted,
            'native_toggle_packet':bool(packets),'native_mask':actual==expected,
            'saved_actions_unchanged':saved_actions(t.fixture['guid'])==t.actions_baseline,
            'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        return {'status':'stock_extra_bar_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'public_setting':value,'native_mask':actual,'native_packets':packets}}
    require(click_case(t,label,'Toggle the observed stock Action Bar2 checkbox.',
        lambda c:c['kind']=='CheckButton' and c.get('setting_variable')==VARIABLE and point(c)==point(button),
        outcome),'stock_extra_bar_pass')


def close(t,label):
    require(click_case(t,label,'Close stock Settings.',lambda c:c['kind']=='Button' and c['text']=='Close',
        lambda b,a,s:{'status':'stock_settings_close_pass' if s and 'SettingsPanel' not in a['panels'] else
            'client_or_protocol_failure'},await_state=lambda s:'SettingsPanel' not in s['panels']),
        'stock_settings_close_pass');t.clean_panels()


def suite(t):
    t.session=actors.session_entry(t.fixture)['session'];oracle=Inventory(lab.ROOT,t.session,t.fixture['guid']).poll()
    t.clean_panels();state,_=t.observe('extra_bar_fixture')
    if state.get('observer_version',0)<71:raise RuntimeError('requires passive settings observer71')
    original=resources(oracle);spells=known(t.fixture['guid']);t.actions_baseline=saved_actions(t.fixture['guid'])
    t.bar_baseline=bars(t,'extra_bar_layout');t.mask_baseline=mask(oracle);layout=None
    t.receipt.update(baseline=original,native_persisted_spells=spells,native_actions=t.actions_baseline,
        bar_baseline=t.bar_baseline,native_mask_baseline=t.mask_baseline,
        qualified_scope='Action Bar2 checkbox on an idle owned fixture, native toggle packet and player-field mask, stock frame visibility and rendered empty grid, unchanged main slots/actions/resources, full settings and bar visibility restoration. Other bars and persistence remain open.');t.persist()
    if t.mask_baseline&1 or t.bar_baseline['frames']['MultiBarBottomLeft'] or t.bar_baseline['toggles'][0]:
        raise RuntimeError('requires Action Bar2 initially disabled')
    try:
        t.settings_search=open_search(t);layout=settings(t,'settings_layout');t.receipt['layout_baseline']=layout;t.persist()
        if layout['values'].get(VARIABLE) is not False or layout['cvars'].get('alwaysShowActionBars')!='0':
            raise RuntimeError('requires disabled Action Bar2 and original hidden empty grids')
        search(t,'Always Show Action Bars','extra_bar.grid.search')
        toggle(t,'alwaysShowActionBars','1','extra_bar.grid.show')
        search(t,'Action Bar 2','actionbars.extra_bars_toggle.search')
        toggle_extra(t,oracle,True,'actionbars.extra_bars_toggle.enable')
        close(t,'extra_bar.inspect_close');visible=bars(t,'extra_bar_visible')
        if (not visible['frames']['MultiBarBottomLeft'] or mask(oracle)!=(t.mask_baseline|1) or
            signature(visible)!=signature(t.bar_baseline) or not visible['toggles'][0]):
            raise RuntimeError('enabled extra bar does not survive panel close')
    except Exception as error:
        t.receipt['execution_failure']=f'{type(error).__name__}: {error}';t.persist();raise
    finally:
        try:
            if layout is not None:
                state,_=t.observe('extra_bar_restore_panels')
                if 'SettingsPanel' not in state['panels']:t.settings_search=open_search(t)
                current=settings(t,'extra_bar_restore_before')
                if current['values'].get(VARIABLE) is not False:
                    search(t,'Action Bar 2','extra_bar.restore_search')
                    toggle_extra(t,oracle,False,'actionbars.extra_bars_toggle.restore')
                current=settings(t,'extra_bar_grid_restore_before')
                if current['cvars'].get('alwaysShowActionBars')!=layout['cvars']['alwaysShowActionBars']:
                    search(t,'Always Show Action Bars','extra_bar.grid.restore_search')
                    toggle(t,'alwaysShowActionBars',layout['cvars']['alwaysShowActionBars'],'extra_bar.grid.restore')
                search(t,layout.get('search') or '','settings.restore_search')
                after=settings(t,'settings_restored');t.receipt['layout_restored']=all(after.get(k)==layout.get(k)
                    for k in ['search','category','cvars','values']);t.persist()
                if not t.receipt['layout_restored']:raise RuntimeError('original settings layout did not restore')
                close(t,'extra_bar.restore_close')
            final=bars(t,'extra_bar_restored');t.receipt['bar_restored']=(final['frames']==t.bar_baseline['frames'] and
                final['toggles']==t.bar_baseline['toggles'] and signature(final)==signature(t.bar_baseline));t.persist()
            if not t.receipt['bar_restored']:raise RuntimeError('original extra-bar visibility did not restore')
        finally:
            t.receipt.update(native_after=resources(oracle),native_mask_after=mask(oracle),
                native_actions_after=saved_actions(t.fixture['guid']),native_persisted_spells_after=known(t.fixture['guid']))
            t.receipt['native_resources_preserved']=(t.receipt['native_after']==original and
                t.receipt['native_mask_after']==t.mask_baseline and t.receipt['native_actions_after']==t.actions_baseline and
                t.receipt['native_persisted_spells_after']==spells);t.persist()
    if not t.receipt['native_resources_preserved']:raise RuntimeError('extra bar trial changed native resources')


def recover(t,source):
    source=source.resolve()
    if source.name!='episode.json' or not source.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('require an owned failed extra-bar episode')
    old=json.loads(source.read_text());t.session=actors.session_entry(t.fixture)['session']
    oracle=Inventory(lab.ROOT,t.session,t.fixture['guid']).poll();layout=old['layout_baseline']
    if (old['actor']!=t.fixture or old['runtime']!=t.receipt['runtime'] or old['completed'] or
        not old.get('finished_at') or old.get('native_resources_preserved') is not True or
        old['failure']!='RuntimeError: RuntimeError: actionbars diagnostic did not become visible' or
        old.get('native_mask_after')!=old['native_mask_baseline'] or mask(oracle)!=old['native_mask_baseline'] or
        resources(oracle)!=old['baseline'] or known(t.fixture['guid'])!=old['native_persisted_spells'] or
        saved_actions(t.fixture['guid'])!=old['native_actions']):
        raise RuntimeError('failed source/runtime/native baseline differs')
    current=settings(t,'cleanup_settings_before')
    unchanged=lambda key: {k:v for k,v in current[key].items() if k!='alwaysShowActionBars'}=={
        k:v for k,v in layout[key].items() if k!='alwaysShowActionBars'}
    if (not current['visible'] or current['category']!=layout['category'] or
        current['search']!='Action Bar 2' or current['values'].get(VARIABLE) is not False or
        current['cvars'].get('alwaysShowActionBars')!='1' or not unchanged('cvars') or not unchanged('values')):
        raise RuntimeError('cleanup is not the exact failed empty-grid state')
    t.settings_search=old['search_field'];t.receipt.update(source={'file':str(source),'sha256':lab.sha256(source)},
        baseline=old['baseline'],native_persisted_spells=old['native_persisted_spells'],
        qualified_scope='Cleanup only: restore the exact failed extra-bar trial empty-grid setting and search, then verify all settings, original bar visibility and native resources. No gameplay qualification.');t.persist()
    search(t,'Always Show Action Bars','cleanup.grid.search')
    toggle(t,'alwaysShowActionBars',layout['cvars']['alwaysShowActionBars'],'cleanup.grid.restore')
    search(t,layout.get('search') or '','cleanup.restore_search')
    after=settings(t,'settings_restored');t.receipt['layout_restored']=all(after.get(k)==layout.get(k)
        for k in ['search','category','cvars','values']);t.persist()
    if not t.receipt['layout_restored']:raise RuntimeError('cleanup settings did not restore')
    close(t,'cleanup.close');final=bars(t,'extra_bar_restored');baseline=old['bar_baseline']
    t.receipt['bar_restored']=(final['frames']==baseline['frames'] and final['toggles']==baseline['toggles'] and
        signature(final)==signature(baseline));t.receipt.update(native_after=resources(oracle),native_mask_after=mask(oracle))
    t.receipt['native_resources_preserved']=(t.receipt['native_after']==old['baseline'] and
        t.receipt['native_mask_after']==old['native_mask_baseline'] and
        known(t.fixture['guid'])==old['native_persisted_spells'] and saved_actions(t.fixture['guid'])==old['native_actions'])
    t.persist()
    if not t.receipt['bar_restored'] or not t.receipt['native_resources_preserved']:
        raise RuntimeError('extra-bar cleanup did not restore original state')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--actor',choices=['primary','scout'],required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--recover-source',type=Path);a=p.parse_args()
    with actor(a.actor):
        t=Trial(a.output,controller='code')
        try:
            if a.recover_source:recover(t,a.recover_source)
            else:suite(t)
            t.receipt['completed']=True
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
        finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
