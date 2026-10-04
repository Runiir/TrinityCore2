"""Use the observed sheath binding with native wire/field and rendered weapon checks."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial,binding_key
from .interaction_actionbar_pages import detail
from .interaction_extra_bar import signature
from .interaction_sit_stand import pose,afk
from .interaction_stance_bar import native_state,restored_native_state
from .interaction_spellbook_recon import resources
from .interaction_spellbook_navigation import known
from .interaction_spellbook_actions import saved_actions
from .interaction_macros import require
from .observation.inventory import Inventory
from .observation.journal import entries


def cycle(original,ranged):
    states=3 if ranged else 2
    if original not in range(states):raise ValueError('sheath state does not match the owned weapon fixture')
    return [(original+i)%states for i in range(1,states+1)]


def select(t,oracle,wanted,label):
    since=time.time()
    def outcome(b,a,selected):
        time.sleep(12)
        bar=detail(t,label+'_value',lambda p:pose(oracle)['sheath']==wanted and
            p['pose'].get('sheath')==wanted+1)
        rows=[{k:r[k] for k in ['time','direction','name','body']} for r in
            entries(lab.ROOT/'evidence/world_packets.jsonl') if r.get('time',0)>=since and
            r.get('session')==t.session and r.get('name')=='CMSG_SET_SHEATHED']
        native=pose(oracle)
        checks={'ordinary_observed_binding':selected=='sheath',
            'modern_request':any(r['direction']=='from_client' and
                r['body'] in [(wanted.to_bytes(4,'little')+bytes([animate])).hex() for animate in [0,128]] for r in rows),
            'native_request':any(r['direction']=='to_native' and r['body']==wanted.to_bytes(4,'little').hex() for r in rows),
            'native_sheath':native['sheath']==wanted,'public_sheath':bar['pose'].get('sheath')==wanted+1,
            'native_stand_unchanged':native['stand']==t.pose_baseline['stand'],
            'idle':bar['pose'].get('speed')==0,'main_bar_unchanged':signature(bar)==signature(t.bar_baseline),
            'position_unchanged':a['world_position']==t.position_baseline,
            'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        return {'status':'native_sheath_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'packets':rows,'native_pose':native,'public':bar}}
    require(t.step(label,'Toggle the owned character weapon through the installed sheath binding.',
        {'sheath':{'kind':'key','value':t.sheath_key,'hold':.4,'description':'Press the observed sheath binding.'}},
        outcome,diagnostic_action='sheath'),'native_sheath_pass')


def suite(t):
    t.session=actors.session_entry(t.fixture)['session'];oracle=Inventory(lab.ROOT,t.session,t.fixture['guid']).poll()
    t.clean_panels();state,_=t.observe('sheath_fixture');t.bar_baseline=detail(t,'sheath_layout')
    t.pose_baseline=pose(oracle);t.position_baseline=state['world_position']
    keys=t.bar_baseline['keys'].get('TOGGLESHEATH')
    ranged=bool(oracle.equipment(18)['id'])
    sequence=cycle(t.pose_baseline['sheath'],ranged)
    if (state.get('observer_version',0)<74 or state.get('framerate',0)<10 or not keys or
        t.pose_baseline['stand'] not in [0,1] or t.bar_baseline['pose'].get('speed')!=0 or
        t.bar_baseline['pose'].get('sheath')!=t.pose_baseline['sheath']+1):
        raise RuntimeError('requires at least10 rendered FPS, an idle owned normal weapon sheath fixture and observed binding')
    t.sheath_key=binding_key(keys[0]);original=resources(oracle);stats=native_state(oracle)
    spells=known(t.fixture['guid']);actions=saved_actions(t.fixture['guid']);original_afk=afk(oracle)
    t.receipt.update(native_session=t.session,baseline=original,native_state_baseline=stats,
        native_persisted_spells=spells,native_actions=actions,pose_baseline=t.pose_baseline,
        native_afk_baseline=original_afk,bar_baseline=t.bar_baseline,position_baseline=t.position_baseline,
        observed_sheath_binding=keys,observed_weapon_cycle=sequence,
        qualified_scope='Observed ordinary sheath binding on one idle owned warrior. Modern five-byte requests, native four-byte requests and native/public sheath states agree. Exact settled weapon frames require visual review. Original pose/AFK/main bar/position and native resources/stats/spells/actions restore. Other weapon modes, combat, races and persistence remain open.');t.persist()
    try:
        for wanted in sequence:select(t,oracle,wanted,'movement.sheath_state_'+str(wanted))
    finally:
        try:
            if pose(oracle)['sheath']!=t.pose_baseline['sheath']:
                for wanted in cycle(pose(oracle)['sheath'],ranged):
                    select(t,oracle,wanted,'movement.sheath_cleanup_'+str(wanted))
                    if wanted==t.pose_baseline['sheath']:break
            if afk(oracle)!=original_afk:t.execute({'kind':'chat','value':'/afk'})
            if pose(oracle)['stand']!=t.pose_baseline['stand']:
                t.execute({'kind':'key','value':binding_key(t.bar_baseline['keys']['SITORSTAND'][0]),'hold':.4})
            time.sleep(12);final,frame=t.observe('sheath_restored');bar=detail(t,'sheath_bar_restored')
            t.receipt['layout_restored']=(pose(oracle)==t.pose_baseline and afk(oracle)==original_afk and
                final['world_position']==t.position_baseline and signature(bar)==signature(t.bar_baseline) and
                bar['pose']==t.bar_baseline['pose'])
            t.receipt['restoration_frame']=frame;t.persist()
        finally:
            t.receipt.update(native_after=resources(oracle),native_state_after=native_state(oracle),
                native_pose_after=pose(oracle),native_afk_after=afk(oracle),
                native_actions_after=saved_actions(t.fixture['guid']),native_persisted_spells_after=known(t.fixture['guid']))
            t.receipt['native_resources_preserved']=(t.receipt['native_after']==original and
                restored_native_state(stats,t.receipt['native_state_after']) and
                t.receipt['native_actions_after']==actions and t.receipt['native_persisted_spells_after']==spells);t.persist()
    if not t.receipt['layout_restored'] or not t.receipt['native_resources_preserved']:
        raise RuntimeError('sheath fixture did not restore native/public state')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--actor',choices=['primary','scout'],required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    with actor(a.actor):
        t=Trial(a.output,controller='code')
        try:suite(t);t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
