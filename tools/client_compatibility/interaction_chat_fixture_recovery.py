"""Cancel only the exact unsubmitted owned invitation and verify restoration."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial,binding_key
from .interaction_targeting import selection
from .interaction_ground_movement import position
from .interaction_actionbar_pages import detail
from .interaction_extra_bar import signature
from .interaction_sit_stand import pose,afk
from .interaction_spellbook_recon import resources
from .interaction_stance_bar import native_state,restored_native_state
from .interaction_spellbook_navigation import known
from .interaction_spellbook_actions import saved_actions
from .interaction_groups import native_group
from .observation.inventory import Inventory


def recover(out,source):
    source=source.resolve();out.mkdir(parents=True,exist_ok=False,mode=0o700)
    if source.name!='owned_assist02' or not source.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('require the exact closed owned invite autocomplete failure')
    cohort=json.loads((source/'cohort.json').read_text())
    if not cohort.get('finished_at') or cohort['failure']!='RuntimeError: chat edit differs from the selected command; refusing submission' or native_group():
        raise RuntimeError('source failure or solo fixture identity differs')
    report={'schema':'client442_chat_fixture_recovery_v1','source':str(source),'completed':False};trials=[]
    try:
        for name in ['primary','scout']:
            with actor(name):
                old=json.loads((source/name/'episode.json').read_text());t=Trial(out/name,controller='code');trials.append(t)
                if old['actor']!=t.fixture or old['runtime']!=t.receipt['runtime']:
                    raise RuntimeError('owned actor or runtime differs from the failed source')
                oracle=Inventory(lab.ROOT,actors.session_entry(t.fixture)['session'],t.fixture['guid']).poll()
                base=old['ground_baseline'];saved=old['bar_details']['ground_layout']['state']['actionbar_probe']
                original_position=position(t.fixture['guid']);state,frame=t.observe('pending_chat')
                if name=='primary':
                    pending=old['chat_submission_checks'][-1]
                    if pending['submitted'] or state.get('chat_edit_text')!=pending['observed_text'] or pending['observed_text']!='/invite Harnesstwo-Client442Lab':
                        raise RuntimeError('pending unsubmitted command differs')
                    t.receipt['pending_source']={'frame':frame,'text':state['chat_edit_text'],'submitted':False};t.persist()
                    t.execute({'kind':'key','value':'Escape','hold':.4})
                    state,_=t.observe('chat_cancelled')
                    if state.get('chat_edit_open'):raise RuntimeError('owned pending chat did not close')
                if afk(oracle)!=base['afk']:t.execute({'kind':'chat','value':'/afk'})
                if pose(oracle)['stand']!=base['pose']['stand']:
                    t.execute({'kind':'key','value':binding_key(saved['keys']['SITORSTAND'][0]),'hold':.4})
                state,frame=t.observe('restored');bar=detail(t,'restored_bar')
                checks={'resources':resources(oracle)==base['resources'],'stats':restored_native_state(base['stats'],native_state(oracle)),
                    'spells':known(t.fixture['guid'])==base['spells'],'actions':saved_actions(t.fixture['guid'])==base['actions'],
                    'pose':pose(oracle)==base['pose'],'afk':afk(oracle)==base['afk'],'main_bar':signature(bar)==signature(saved),
                    'target_cleared':selection(oracle)==0 and not state['target'].get('exists'),
                    'solo':native_group() is None and state['group']['members']==0,'idle':bar['pose']['speed']==0,
                    'chat_closed':not state.get('chat_edit_open'),'native_position_preserved':position(t.fixture['guid'])==original_position}
                t.receipt['source_restoration']={'checks':checks,'frame':frame,'qualification':False};t.persist()
                if not all(checks.values()):raise RuntimeError('source fixture restoration differs')
                t.receipt['completed']=True
        report['completed']=True
    except Exception as error:report['failure']=f'{type(error).__name__}: {error}'
    finally:
        for t in trials:t.receipt.update(finished_at=time.time(),failure=report.get('failure'));t.persist()
        report['finished_at']=time.time();lab.private_write(out/'cohort.json',json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--source',type=Path,required=True)
    a=p.parse_args();recover(a.output,a.source)
