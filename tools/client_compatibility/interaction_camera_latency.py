"""Use ordinary camera-wheel bindings and inspect the stock latency tooltip."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_social import actor
from .interaction_macros import require
from .interaction_operations import controls,point,command
from .interaction_tooltips import tooltip
from .interaction_actionbar_pages import detail
from .interaction_camera_fixture import set_zoom
from .interaction_spellbook_recon import resources
from .interaction_spellbook_navigation import known
from .observation.inventory import Inventory


def wheel(t,direction,label,expected=None):
    before=detail(t,label+'_before');value=before['camera_zoom'];button=4 if direction<0 else 5
    def ready(p):
        current=p.get('camera_zoom',value)
        return abs(current-expected)<.1 if expected is not None else (current-value)*direction>.25
    def outcome(b,a,s):
        probe=detail(t,label+'_changed',ready)
        checks={'ordinary_wheel_binding':s=='wheel','requested_zoom':ready(probe),
            'world_position_unchanged':a.get('world_position')==b.get('world_position'),
            'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        return {'status':'stock_camera_zoom_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'zoom_before':value,'zoom_after':probe['camera_zoom']}}
    require(t.step(label,'Zoom through the installed ordinary mouse-wheel camera binding.',
        {'wheel':{'kind':'click','value':[1000,360],'button':button,
            'description':'Send one observed camera wheel binding over clear world space.'}},
        outcome,diagnostic_action='wheel'),'stock_camera_zoom_pass')


def latency(t):
    # Read-only hook installation occurs on the passive action-bar page. Move
    # away first so the later hover produces a distinct stock tooltip event.
    t.receipt['latency_setup_input']={'kind':'hover','value':[1000,360]};t.persist()
    t.execute(t.receipt['latency_setup_input']);layout=detail(t,'latency_before')
    previous=(layout.get('performance_event') or {}).get('time',-1)
    rows=[c for c in controls(t) if c['name']=='MainMenuMicroButton']
    if len(rows)!=1:raise RuntimeError('the stock main-menu latency control is absent or ambiguous')
    control=rows[0]
    def outcome(b,a,s):
        probe=tooltip(t,'latency_tooltip');event=probe.get('performance_event') or {}
        texts=[line.get('left','') for line in probe.get('lines') or []]
        checks={'ordinary_hover':s=='hover','stock_tooltip_visible':probe.get('visible') is True,
            'observed_owner':probe.get('owner')==control['name']==event.get('owner'),
            'fresh_stock_tooltip_event':event.get('time',-1)>previous,
            'public_latency_numbers':all(isinstance(event.get(k),(int,float)) and event[k]>=0 for k in ['home','world']),
            'exact_formatted_latency_line':bool(event.get('expected_line') and event['expected_line'] in texts),
            'no_format_placeholder':not any('%d' in text or '%s' in text for text in texts),
            'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        return {'status':'stock_latency_display_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'public':probe}}
    require(t.step('ui_misc.latency_display','Inspect the stock home/world latency tooltip through ordinary pointer movement.',
        {'hover':{'kind':'hover','value':point(control),'description':'Hover the observed main-menu microbutton.'}},
        outcome,diagnostic_action='hover'),'stock_latency_display_pass')
    t.execute({'kind':'hover','value':[1000,360]})


def suite(t):
    session=actors.session_entry(t.fixture)['session'];oracle=Inventory(lab.ROOT,session,t.fixture['guid']).poll()
    t.clean_panels();state,_=t.observe('camera_latency_fixture')
    if state.get('observer_version',0)<69:raise RuntimeError('requires read-only observer69')
    original=resources(oracle);spells=known(t.fixture['guid']);layout=detail(t,'camera_layout')
    zoom=layout['camera_zoom'];keys=layout['keys']
    if keys.get('CAMERAZOOMIN')!=['MOUSEWHEELUP'] or keys.get('CAMERAZOOMOUT')!=['MOUSEWHEELDOWN']:
        raise RuntimeError('requires the installed ordinary wheel camera bindings')
    if not isinstance(zoom,(int,float)) or not 2<zoom<20:raise RuntimeError('requires an unclamped reversible camera distance')
    t.receipt.update(baseline=original,native_persisted_spells=spells,layout_baseline=layout,
        qualified_scope='One ordinary wheel step in and inverse step out at an idle owned fixture, with original camera distance and native resources restored. Stock main-menu tooltip displays the exact formatted home/world public latency line. Camera presets, performance thresholds and disconnection behavior remain open.');t.persist()
    try:
        wheel(t,-1,'ui_misc.zoom_camera.in')
        wheel(t,1,'ui_misc.zoom_camera.out',expected=zoom)
        latency(t)
    finally:
        try:
            command(t,'/tcui state')
            current=detail(t,'camera_restore_before')
            if abs(current['camera_zoom']-zoom)>=.1:set_zoom(t,zoom,'camera_cleanup_restore',tolerance=.1)
            after=detail(t,'camera_restored');t.receipt['camera_restored']=abs(after['camera_zoom']-zoom)<.1;t.persist()
            if not t.receipt['camera_restored']:raise RuntimeError('original camera distance did not restore')
            t.execute({'kind':'hover','value':[1000,360]});t.clean_panels()
        finally:
            t.receipt.update(native_after=resources(oracle),native_persisted_spells_after=known(t.fixture['guid']))
            t.receipt['native_resources_preserved']=(t.receipt['native_after']==original and t.receipt['native_persisted_spells_after']==spells);t.persist()
    if not t.receipt['native_resources_preserved']:raise RuntimeError('camera/latency inspection changed native resources')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--actor',choices=['primary','scout'],required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    with actor(a.actor):
        t=Trial(a.output,controller='code')
        try:suite(t);t.receipt['completed']=True
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
        finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
