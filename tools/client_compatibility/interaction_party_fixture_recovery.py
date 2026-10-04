"""Restore the exact closed Party-chat observer-capacity failure fixture."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial,binding_key
from .interaction_social import actor
from .interaction_ground_movement import position,native_group,restore_party
from .interaction_actionbar_pages import detail
from .interaction_extra_bar import signature
from .interaction_spellbook_recon import resources
from .interaction_stance_bar import native_state,restored_native_state
from .interaction_spellbook_navigation import known
from .interaction_spellbook_actions import saved_actions
from .interaction_sit_stand import pose,afk
from .observation.inventory import Inventory


def recover(out,source,party_removed_source=None):
    source=source.resolve()
    if not source.is_relative_to(lab.ROOT/'evidence') or source.name!='owned_party_chat05':
        raise ValueError('require the exact owned Party-chat capacity failure')
    cohort=json.loads((source/'cohort.json').read_text())
    if cohort['completed'] or not cohort.get('finished_at') or not cohort.get('cleanup_failures',{}).get('party'):
        raise RuntimeError('require the closed failed party cleanup')
    originals={a:json.loads((source/a/'episode.json').read_text()) for a in ['primary','scout']}
    restored_positions=json.loads((source/'nearby_restoration.json').read_text())['positions']
    removed=None
    if party_removed_source:
        party_removed_source=party_removed_source.resolve()
        if party_removed_source!=source.parent/'party_fixture_recovery02':raise ValueError('require exact prior party-removal recovery')
        prior=json.loads((party_removed_source/'recovery.json').read_text())
        scout=json.loads((party_removed_source/'scout/episode.json').read_text())
        if (prior['completed'] or not prior.get('finished_at') or prior['failure']!='RuntimeError: UI observation did not become decodable' or
                scout['runtime']!=originals['scout']['runtime'] or not scout.get('party_restoration',{}).get('native_absent') or
                not scout['party_restoration'].get('visible_solo') or not all(scout['source_restoration']['checks'].values())):
            raise RuntimeError('prior party-removal evidence differs')
        removed={'file':str(party_removed_source/'recovery.json'),'sha256':lab.sha256(party_removed_source/'recovery.json')}
    out.mkdir(parents=True,exist_ok=False,mode=0o700);report={'qualification':False,'completed':False,'failure':None,
        'source':{'file':str(source/'cohort.json'),'sha256':lab.sha256(source/'cohort.json')}};trials={}
    try:
        for a in ['scout','primary']:
            with actor(a):
                t=trials[a]=Trial(out/a,controller='code');old=originals[a]
                if t.fixture!=old['actor'] or t.receipt['runtime']!=old['runtime']:
                    raise RuntimeError('source actor or owned runtime changed')
                if position(t.fixture['guid'])!=restored_positions[str(t.fixture['guid'])]:
                    raise RuntimeError('source fixture position differs before recovery')
        with actor('scout'):
            t=trials['scout'];state,frame=t.observe('before_party_leave')
            if removed:
                if state['group']['members']!=0 or native_group() is not None:raise RuntimeError('verified removed party reappeared')
                t.receipt['party_already_removed_source']=removed;t.persist()
            else:
                if state['group']['members']!=2 or native_group()['members']!=[1,2]:
                    raise RuntimeError('expected exact leftover owned two-member party')
                t.receipt['party_restoration']=restore_party(t);t.persist()
        for a,t in trials.items():
            with actor(a):
                old=originals[a];base=old['ground_baseline'];session=actors.session_entry(t.fixture)['session']
                oracle=Inventory(lab.ROOT,session,t.fixture['guid']).poll();t.clean_panels();state,_=t.observe('recovery_state')
                if state['target'].get('exists'):t.execute({'kind':'key','value':'Escape','hold':.4})
                if afk(oracle)!=base['afk']:t.execute({'kind':'chat','value':'/afk'})
                bar=detail(t,'recovery_bar')
                if pose(oracle)['stand']!=base['pose']['stand']:
                    if {pose(oracle)['stand'],base['pose']['stand']}!={0,1}:raise RuntimeError('unsupported source pose')
                    t.execute({'kind':'key','value':binding_key(bar['keys']['SITORSTAND'][0]),'hold':.4})
                time.sleep(12);state,frame=t.observe('source_restored');bar=detail(t,'source_bar_restored')
                checks={'resources':resources(oracle)==base['resources'],
                    'stats':restored_native_state(base['stats'],native_state(oracle)),
                    'spells':known(t.fixture['guid'])==base['spells'],'actions':saved_actions(t.fixture['guid'])==base['actions'],
                    'pose':pose(oracle)==base['pose'],'afk':afk(oracle)==base['afk'],
                    'main_bar':signature(bar)==signature(old['bar_details']['ground_layout']['state']['actionbar_probe']),
                    'target_cleared':not state['target'].get('exists'),'solo_group_restored':state['group']['members']==0,
                    'idle':bar['pose'].get('speed')==0}
                checks['position']=position(t.fixture['guid'])==restored_positions[str(t.fixture['guid'])]
                t.receipt['source_restoration']={'checks':checks,'frame':frame};t.persist()
                if not all(checks.values()):raise RuntimeError('exact source fixture differs after recovery')
        report['completed']=True
    except Exception as error:report['failure']=f'{type(error).__name__}: {error}'
    finally:
        for t in trials.values():t.receipt.update(completed=report['completed'],failure=report['failure'],finished_at=time.time());t.persist()
        report['finished_at']=time.time();lab.private_write(out/'recovery.json',json.dumps(report,indent=2)+'\n')
        print(json.dumps(report),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--party-removed-source',type=Path)
    a=p.parse_args();recover(a.output,a.source,a.party_removed_source)
