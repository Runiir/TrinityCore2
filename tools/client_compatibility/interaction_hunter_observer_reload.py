"""Reload only the retained Hunter's passive observer at a restored stable boundary."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_owned_class_fixture import SCRIPT_BOUNDARY
from .interaction_retained_class_fixture import closed
from .interaction_retained_class_reentry import install_observer
from .interaction_hunter_stable_capture import eligibility,staged,restore


def run(t,preparation,entry,source):
    old,session,npc,o,inv,retained=eligibility(t,preparation,entry)
    previous=closed(source)
    if (previous.get('actor')!=t.fixture or previous.get('runtime')!=t.receipt['runtime'] or
        previous.get('phase')!='hunter_stable_request_staged' or previous.get('native_session')!=session or
        previous.get('fixture_source',{}).get('sha256')!=lab.sha256(preparation)):
        raise RuntimeError('requires the closed current Hunter stable staging')
    before,frame,guid=staged(t,npc,o,'before_reload')
    if (guid!=previous['native_master_guid'] or before['world_position']!=previous['state']['world_position']):
        raise RuntimeError('restored Hunter selection or pose differs')
    t.receipt.update(source={'path':str(source.resolve()),'sha256':lab.sha256(source)},before=before,
        before_frame=frame,input_sent=False);t.persist()
    install_observer(t,143)
    t.receipt['input_sent']=True;t.persist()
    t.execute({'kind':'chat','value':'/reload'})
    state,frame=t.observe('after_reload',seconds=60)
    checks={'passive_observer143':state.get('observer_version')==143,
        'same_native_session':actors.session_entry(t.fixture)['session']==session,
        'owned_guid':state['guid']==t.guid,'ui_clean':not state.get('lua_errors') and not state.get('blocked_actions')}
    t.receipt.update(state=state,frame=frame,checks=checks);t.persist()
    restore(t,old,previous,o,inv,retained)
    if not all(checks.values()):raise RuntimeError('passive scout reload differs')
    t.receipt.update(completed=True,phase='hunter_passive_mouse_observer_loaded',qualification_added=False)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('preparation','entry','source','output'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2,chat_open_retry=True)
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:run(t,a.preparation,a.entry,a.source)
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','phase','failure','checks','restoration_checks')}),flush=True)
