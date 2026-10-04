"""Exercise stock FPS, screenshot and UI-visibility bindings on an owned client."""
import argparse,json,re,shutil,time
from pathlib import Path
from PIL import Image
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial,binding_key
from .interaction_macros import require
from .interaction_bridge_deploy import shot
from .interaction_spellbook_recon import resources
from .interaction_spellbook_navigation import known
from .observation.inventory import Inventory
from .observation.interactions import decode_image


def fps(t,wanted,label,key):
    def outcome(b,a,s):
        text=a.get('framerate_text') or '';numbers=re.findall(r'\d+(?:\.\d+)?',text)
        valid={'single_binding':s=='toggle','visible':a.get('framerate_visible')==wanted,
            'numeric_display':not wanted or bool(numbers and float(numbers[0])>0),
            'public_fps':not wanted or (a.get('framerate') or 0)>0,
            'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        return {'status':'fps_display_pass' if all(valid.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':valid,'display':text,'public_fps':a.get('framerate')}}
    require(t.step('ui_misc.fps_display.'+label,'Toggle the stock FPS display through its installed binding.',
        {'toggle':{'kind':'key','value':key,'description':'Press the observed FPS binding.'}},
        outcome,diagnostic_action='toggle',await_state=lambda s:s.get('framerate_visible')==wanted),'fps_display_pass')


def screenshot(t,key):
    directory=lab.client_root()/'client/_whitemane-60895_/Screenshots'
    before={p.name for p in directory.iterdir()} if directory.exists() else set()
    def outcome(b,a,s):
        deadline=time.monotonic()+16
        while True:
            fresh=[p for p in directory.iterdir() if p.name not in before] if directory.exists() else []
            if fresh:break
            if time.monotonic()>deadline:raise RuntimeError('normal screenshot binding produced no file')
            time.sleep(.2)
        if len(fresh)!=1 or not fresh[0].is_file() or fresh[0].is_symlink():raise RuntimeError('screenshot result is ambiguous')
        source=fresh[0];target=t.out/source.name
        with Image.open(source) as picture:
            dimensions=picture.size;picture.verify()
        shutil.move(source,target)
        return {'status':'client_screenshot_pass' if s=='capture' and dimensions==(1280,720) else 'client_or_protocol_failure',
            'oracle':{'ordinary_saved_screenshot':{'file':target.name,'sha256':lab.sha256(target)},
                'original_private_path':str(source),'dimensions':dimensions,'only_new_file':True}}
    require(t.step('ui_misc.screenshot','Save a game screenshot through the installed screenshot binding.',
        {'capture':{'kind':'key','value':key,'description':'Press the observed game screenshot binding on the private display.'}},
        outcome,diagnostic_action='capture'),'client_screenshot_pass')


def toggle_ui(t,key):
    state,frame=t.observe('ui_visible_baseline');row={'id':'ui_misc.toggle_ui','goal':'Hide and restore the stock interface with its installed binding.',
        'time':time.time(),'status':'started','before':state,'before_frame':frame,'input':{'kind':'key','value':key}}
    t.receipt['cases'].append(row);t.persist();hidden=False
    try:
        t.execute(row['input']);deadline=time.monotonic()+16
        while True:
            picture=shot(t.out/'ui_hidden.png')
            with Image.open(t.out/'ui_hidden.png') as capture:
                try:decode_image(capture)
                except ValueError as e:
                    if str(e)=='UI observation marker is missing':hidden=True;break
                    raise
            if time.monotonic()>deadline:raise RuntimeError('UI visibility binding did not hide its parent; refusing input replay')
            time.sleep(.2)
        row['hidden_frame']=picture;t.persist()
    finally:
        if hidden:
            t.execute({'kind':'key','value':key});after,frame=t.observe('ui_restored',seconds=60)
            row.update(after=after,after_frame=frame,restoration_input={'kind':'key','value':key},
                status='ui_visibility_pass' if after['guid']==state['guid'] and not after.get('lua_errors') and
                    not after.get('blocked_actions') else 'client_or_protocol_failure')
            t.persist()
    require(row,'ui_visibility_pass')


def suite(t):
    session=actors.session_entry(t.fixture)['session'];oracle=Inventory(lab.ROOT,session,t.fixture['guid']).poll()
    t.clean_panels();state,frame=t.observe('display_baseline')
    if state.get('observer_version',0)<64:raise RuntimeError('requires passive display observer64')
    keys={name:state.get(name) or [] for name in ['fps_keys','toggle_ui_keys','screenshot_keys']}
    if any(not value for value in keys.values()):raise RuntimeError('required stock display binding is unavailable')
    fps_key=binding_key(keys['fps_keys'][0]);ui_key=binding_key(keys['toggle_ui_keys'][0])
    capture_key=binding_key(keys['screenshot_keys'][0]).replace('PRINTSCREEN','Print')
    original=resources(oracle);spells=known(t.fixture['guid']);visible=state['framerate_visible']
    t.receipt.update(baseline=original,native_persisted_spells=spells,display_baseline={'state':state,'frame':frame},
        qualified_scope='Installed stock FPS toggle and rendered numeric value, one game-generated screenshot, and UI hide/restore with exact frames. Other display settings and cinematic/movie dialogs remain open.');t.persist()
    try:
        fps(t,not visible,'change',fps_key);fps(t,visible,'restore',fps_key)
        screenshot(t,capture_key);toggle_ui(t,ui_key)
    finally:
        try:
            after,_=t.observe('display_cleanup',seconds=60)
            if after['framerate_visible']!=visible:fps(t,visible,'cleanup',fps_key)
            t.clean_panels()
        finally:
            t.receipt.update(native_after=resources(oracle),native_persisted_spells_after=known(t.fixture['guid']))
            t.receipt['native_resources_preserved']=t.receipt['native_after']==original and t.receipt['native_persisted_spells_after']==spells
            t.persist()
            if not t.receipt['native_resources_preserved']:raise RuntimeError('display controls changed native inventory/money/spells')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--actor',choices=['primary','scout'],required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    with actor(a.actor):
        t=Trial(a.output,controller='code')
        try:suite(t);t.receipt['completed']=True
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
        finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
