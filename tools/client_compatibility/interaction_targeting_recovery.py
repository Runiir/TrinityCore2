"""Restore the exact owned fixture left by the observer76 self-target overflow."""
import argparse,json,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial,binding_key
from .interaction_targeting import selection
from .interaction_ground_movement import restore_party,position
from .interaction_groups import native_group
from .interaction_actionbar_pages import detail
from .interaction_extra_bar import signature
from .interaction_sit_stand import pose,afk
from .interaction_spellbook_recon import resources
from .interaction_stance_bar import native_state,restored_native_state
from .interaction_spellbook_navigation import known
from .interaction_spellbook_actions import saved_actions
from .interaction_bridge_deploy import shot
from .observation.inventory import Inventory
from . import actors


def recover(out,source):
    source=source.resolve()
    if not source.is_relative_to(lab.ROOT/'evidence') or source.name!='owned_targeting02':
        raise ValueError('require the attributable owned observer-overflow cohort')
    cohort=json.loads((source/'cohort.json').read_text())
    if cohort['completed'] or cohort['failure']!='RuntimeError: UI state observation deadline exceeded':
        raise RuntimeError('source failure differs')
    group=native_group()
    if not group or group['members']!=[1,2] or group['leader']!=1 or group['type']!=0:
        raise RuntimeError('leftover party identity differs')
    report={'schema':'client442_targeting_recovery_v1','source':str(source),'completed':False}
    trials={};original={};oracles={}
    try:
        for name in ['primary','scout']:
            with actor(name):
                old=original[name]=json.loads((source/name/'episode.json').read_text())
                t=trials[name]=Trial(out/name,controller='code')
                if old['actor']!=t.fixture or old['runtime']!=t.receipt['runtime']:
                    raise RuntimeError('source actor or runtime changed')
                session=actors.session_entry(t.fixture)['session']
                oracle=oracles[name]=Inventory(lab.ROOT,session,t.fixture['guid']).poll()
                if resources(oracle)!=old['ground_baseline']['resources']:
                    raise RuntimeError('native resources changed since the failed fixture')
                expected=json.loads((source/'nearby_restoration.json').read_text())['positions'][str(t.fixture['guid'])]
                if any(abs(a-b)>.01 for a,b in zip(position(t.fixture['guid']),expected)):
                    raise RuntimeError('failed fixture native position is not already restored')
        with actor('primary'):
            t=trials['primary'];oracle=oracles['primary']
            if selection(oracle)!=1:raise RuntimeError('overflow recovery requires the exact self target')
            frame=shot(t.out/'self_target_overflow.png')
            row={'id':'fixture.clear_self_target','selection_source':'code','qualification':False,
                'before_native_target':1,'before_frame':frame,
                'input':{'kind':'key','value':'Escape','hold':.4}}
            t.receipt['cases'].append(row);t.persist()
            t.io.key('Escape',hold=.4);time.sleep(1)
            state,frame=t.observe('target_cleared')
            row.update(after_frame=frame,checks={'native_target_cleared':selection(oracle)==0,
                'public_target_cleared':not state['target'].get('exists')})
            row['status']='fixture_cleanup_pass' if all(row['checks'].values()) else 'cleanup_failure';t.persist()
            if not all(row['checks'].values()):raise RuntimeError('self target did not clear')
            report['party']=restore_party(t)
        for name in ['primary','scout']:
            with actor(name):
                t=trials[name];oracle=oracles[name];base=original[name]['ground_baseline']
                bar=detail(t,'recovery_bar_before')
                if afk(oracle)!=base['afk']:t.execute({'kind':'chat','value':'/afk'})
                if pose(oracle)['stand']!=base['pose']['stand']:
                    t.execute({'kind':'key','value':binding_key(bar['keys']['SITORSTAND'][0]),'hold':.4})
                time.sleep(12);state,frame=t.observe('restored');bar=detail(t,'recovery_bar_restored')
                saved=original[name]['bar_details']['ground_layout']['state']['actionbar_probe']
                checks={'resources':resources(oracle)==base['resources'],
                    'stats':restored_native_state(base['stats'],native_state(oracle)),
                    'spells':known(t.fixture['guid'])==base['spells'],
                    'actions':saved_actions(t.fixture['guid'])==base['actions'],
                    'pose':pose(oracle)==base['pose'],'afk':afk(oracle)==base['afk'],
                    'main_bar':signature(bar)==signature(saved),
                    'target_cleared':selection(oracle)==0 and not state['target'].get('exists'),
                    'solo':native_group() is None and state['group']['members']==0,
                    'idle':bar['pose']['speed']==0}
                t.receipt['source_restoration']={'checks':checks,'frame':frame};t.persist()
                if not all(checks.values()):raise RuntimeError('source fixture restoration differs')
                t.receipt['completed']=True
        report['completed']=True
    except Exception as error:report['failure']=f'{type(error).__name__}: {error}'
    finally:
        for t in trials.values():
            t.receipt.update(finished_at=time.time(),failure=report.get('failure'));t.persist()
        report['finished_at']=time.time();lab.private_write(out/'cohort.json',json.dumps(report,indent=2)+'\n')
        print(json.dumps(report),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--source',type=Path,required=True);a=p.parse_args();recover(a.output,a.source)
