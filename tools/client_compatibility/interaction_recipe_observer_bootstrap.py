"""Recover the source-bound UI86 recipe observer overflow without restarting clients."""
import argparse,json,shutil,time
from pathlib import Path
from . import actors,lab_runtime as lab,owned_input
from .interaction_profession_recipes import RecipeTrial,restore_source
from .interaction_social import actor
from .interaction_bridge_restoration import capture
from .interaction_stance_bar import restored_native_state
from .interaction_trial import binding_key
from .interaction_actionbar_pages import detail as bar_detail
from .interaction_keybindings_native import suite as native_suite


def sources(t,failed,baseline):
    values=[]
    for path in (failed,baseline):
        path=path.resolve()
        if path.name!='episode.json' or not path.is_relative_to(lab.ROOT/'evidence'):
            raise ValueError('requires private owned recipe episodes')
        value=json.loads(path.read_text())
        if (value.get('completed') or not value.get('finished_at') or value['actor']!=t.fixture or
            value['runtime']!=t.receipt['runtime'] or not value.get('native_resources_preserved')):
            raise RuntimeError('closed failed recipe source differs')
        values.append(value)
    failed_value,old=values;checks=old.get('native_restoration',{}).get('checks',{})
    if len(checks)!=10 or not all(checks.values()) or failed_value['native_baseline']!=old['native_baseline']:
        raise RuntimeError('recipe sources lack the shared restored baseline')
    if 'recipe_recon' in failed_value or failed_value.get('observer_file_sha256')!=old.get('observer_file_sha256'):
        raise RuntimeError('requires the same failed in-memory recipe observer')
    return old


def native_checks(current,expected,include_pose=False):
    keys=['resources','spells','actions','position']+(['pose','afk'] if include_pose else [])
    return {**{k:current[k]==expected[k] for k in keys},
        'stats':restored_native_state(expected['stats'],current['stats'])}


def controls_guard(t,label,ready):
    deadline=time.monotonic()+40
    while True:
        state,frame=t.observe(label,mode='controls',seconds=12)
        move=frame['movement']
        t.receipt.setdefault('bootstrap_control_guards',[]).append({'label':label,'frame':frame,
            'observer_version':state.get('observer_version'),'panels':state.get('panels'),
            'chat_edit_open':state.get('chat_edit_open'),'chat_edit_text':state.get('chat_edit_text')});t.persist()
        # Stock controls projection omits observer version and error lists.
        # Bind the old installed source before staging; reload validates the full new state.
        if (state.get('observer_version') not in (None,104) or state.get('lua_errors') or state.get('blocked_actions') or
            move['in_combat'] or move['dead'] or move['on_taxi'] or move['health_percent']!=100 or move['speed']!=0):
            raise RuntimeError('source-bound observer104 idle controls differ')
        if ready(state):return state,frame
        if time.monotonic()>deadline:raise RuntimeError('source-bound observer104 controls did not settle')
        time.sleep(.2)


def prepare(t,failed,baseline):
    old=sources(t,failed,baseline);expected=old['native_baseline']
    if t.receipt['observer_file_sha256']!=old['observer_file_sha256']:
        raise RuntimeError('installed failed observer source changed before staging')
    checks=native_checks(capture(t),expected)
    t.receipt['source_native_checks']=checks;t.persist()
    if not all(checks.values()):raise RuntimeError('native recipe resources changed')
    _,before=controls_guard(t,'bootstrap_closed_alchemy',lambda s:
        s.get('panels')==['SpellBookFrame'] and not s.get('chat_edit_open'))
    t.receipt['before_frame']=before;t.persist()
    t.execute({'kind':'key','value':'Escape','hold':1.2})
    _,closed=controls_guard(t,'bootstrap_closed_book',lambda s:not s.get('panels') and not s.get('chat_edit_open'))
    t.receipt.update(bootstrap_baseline=capture(t),bootstrap_session=actors.session_entry(t.fixture)['session'],
        source_files=[{'path':str(p.resolve()),'sha256':lab.sha256(p)} for p in (failed,baseline)],closed_book_frame=closed)
    src=lab.REPO/'tools/client_compatibility/observation/addon/ClientMovementHarness'
    dst=lab.client_root()/'client/_whitemane-60895_/Interface/AddOns/ClientMovementHarness'
    if 'observer_version=105' not in (src/'ClientInteractions.lua').read_text():
        raise RuntimeError('requires observer105 source')
    shutil.copytree(src,dst,dirs_exist_ok=True)
    t.receipt['installed_observer_sha256']=lab.sha256(dst/'ClientInteractions.lua');t.persist()
    with owned_input.lease():t.io.key('Return',hold=1.2)
    controls_guard(t,'bootstrap_chat_open',lambda s:s.get('chat_edit_open') and s.get('chat_edit_focused'))
    with owned_input.lease():t.io.type('/reload')
    _,pending=controls_guard(t,'pending_reload',lambda s:s.get('chat_edit_open') and
        s.get('chat_edit_focused') and s.get('chat_edit_text')=='/reload')
    t.receipt.update(prepared=True,pending_command='/reload',pending_frame=pending,pending_at=time.time(),
        qualification='Source-bound observer recovery only. No player operation qualified.')


def submit(t,out,reviewed):
    if not reviewed:raise ValueError('requires actual visual review of pending /reload')
    prepared=out/'episode.json';old=json.loads(prepared.read_text())
    if (not old.get('prepared') or old.get('failure') or old.get('pending_command')!='/reload' or
        not 0<=time.time()-old['pending_at']<=120):
        raise RuntimeError('staged reload is absent, failed or expired')
    if old['actor']!=t.fixture or old['runtime']!=t.receipt['runtime']:
        raise RuntimeError('owned runtime changed since staging')
    if lab.sha256(out/old['pending_frame']['file'])!=old['pending_frame']['sha256']:
        raise RuntimeError('reviewed pending frame changed')
    paths=[Path(s['path']) for s in old['source_files']]
    if any(lab.sha256(p)!=s['sha256'] for p,s in zip(paths,old['source_files'])):
        raise RuntimeError('failed source episode changed')
    original=sources(t,*paths);expected=original['native_baseline']
    checks=native_checks(capture(t),old['bootstrap_baseline'],include_pose=True)
    t.receipt.update(prepared_source={'path':str(prepared),'sha256':lab.sha256(prepared)},
        staged_native_checks=checks);t.persist()
    if not all(checks.values()) or actors.session_entry(t.fixture)['session']!=old['bootstrap_session']:
        raise RuntimeError('staged native character or session changed')
    installed=lab.client_root()/'client/_whitemane-60895_/Interface/AddOns/ClientMovementHarness/ClientInteractions.lua'
    if lab.sha256(installed)!=old['installed_observer_sha256']:raise RuntimeError('installed observer changed')
    controls_guard(t,'reviewed_pending_reload',lambda s:s.get('chat_edit_open') and
        s.get('chat_edit_focused') and s.get('chat_edit_text')=='/reload')
    with owned_input.lease():t.io.key('Return',hold=1.2)
    state,frame=t.observe('observer105_reloaded',seconds=240)
    t.receipt['reloaded_frame']=frame;t.persist()
    if (state.get('observer_version')!=105 or state.get('lua_errors') or state.get('blocked_actions') or
        state.get('panels') or state.get('chat_edit_open') or
        actors.session_entry(t.fixture)['session']!=old['bootstrap_session']):
        raise RuntimeError('reloaded observer, session or idle UI differs')
    current=capture(t)
    if not all(native_checks(current,expected).values()):raise RuntimeError('reload changed native resources')
    if current['afk']!=expected['afk']:t.execute({'kind':'chat','value':'/afk'})
    current=capture(t)
    if current['pose']!=expected['pose']:
        if ({current['pose']['stand'],expected['pose']['stand']}!={0,1} or
            current['pose']['sheath']!=expected['pose']['sheath']):raise RuntimeError('unsupported source pose')
        bar=bar_detail(t,'original_recipe_pose_binding')
        t.execute({'kind':'key','value':binding_key(bar['keys']['SITORSTAND'][0]),'hold':1.2});time.sleep(12)
    checks=native_checks(capture(t),expected,include_pose=True)
    t.receipt['original_native_checks_before_suite']=checks;t.persist()
    if not all(checks.values()):raise RuntimeError('original native fixture differs')
    native_suite(t,operations=lambda t:restore_source(t,paths[1]),preserve_settings=False)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','submit'])
    p.add_argument('--output',type=Path,required=True);p.add_argument('--failed',type=Path);p.add_argument('--baseline',type=Path)
    p.add_argument('--reviewed-pending-reload',action='store_true');a=p.parse_args();out=a.output.resolve()
    if not out.is_relative_to(lab.ROOT/'evidence'):p.error('requires private evidence output')
    with actor('primary'):
        t=RecipeTrial(out if a.action=='prepare' else out/'submit',controller='code')
        try:
            if a.action=='prepare':prepare(t,a.failed,a.baseline)
            else:submit(t,out,a.reviewed_pending_reload);t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:
            t.receipt['finished_at']=time.time();t.persist()
            print(json.dumps({k:t.receipt.get(k) for k in ('prepared','completed','failure')}),flush=True)


if __name__=='__main__':main()
