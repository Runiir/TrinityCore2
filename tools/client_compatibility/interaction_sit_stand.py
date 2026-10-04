"""Exercise the installed sit/stand binding with native request, update and pose checks."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial,binding_key
from .interaction_actionbar_pages import detail
from .interaction_extra_bar import signature
from .interaction_stance_bar import native_state,restored_native_state
from .interaction_spellbook_recon import resources
from .interaction_spellbook_navigation import known
from .interaction_spellbook_actions import saved_actions
from .interaction_macros import require
from .observation.inventory import Inventory
from .observation.journal import entries
from .world.objects import INDEX


def pose(oracle):
    oracle.poll();fields=oracle.objects[oracle.guid]
    return {'stand':fields.get(INDEX['UNIT_FIELD_BYTES_1'],0)&255,
        'sheath':fields.get(INDEX['UNIT_FIELD_BYTES_2'],0)&255}


def afk(oracle):
    oracle.poll();return bool(oracle.objects[oracle.guid].get(INDEX['PLAYER_FLAGS'],0)&2)


def select(t,oracle,wanted,label):
    since=time.time()
    def outcome(b,a,s):
        public=detail(t,label+'_value',lambda p:pose(oracle)['stand']==wanted)
        native=pose(oracle)
        packets=[{k:r[k] for k in ['time','direction','name','body']} for r in
            entries(lab.ROOT/'evidence/world_packets.jsonl') if r.get('time',0)>=since and
            r.get('session')==t.session and r.get('name') in ['CMSG_STANDSTATECHANGE','SMSG_STAND_STATE_UPDATE']]
        checks={'ordinary_observed_binding':s=='pose',
            'native_request':any(r['direction']=='to_native' and r['name']=='CMSG_STANDSTATECHANGE' and
                r['body']==wanted.to_bytes(4,'little').hex() for r in packets),
            'native_update':any(r['direction']=='from_native' and r['name']=='SMSG_STAND_STATE_UPDATE' and
                r['body']==bytes([wanted]).hex() for r in packets),
            'native_pose':native['stand']==wanted,'native_sheath_unchanged':native['sheath']==t.pose_baseline['sheath'],
            'public_sheath_agrees':public['pose'].get('sheath')==native['sheath']+1,
            'idle':public['pose'].get('speed')==0,'main_bar_unchanged':signature(public)==signature(t.bar_baseline),
            'position_unchanged':a.get('world_position')==t.position_baseline,
            'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        return {'status':'native_sit_stand_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'native_pose':native,'native_packets':packets,'public':public}}
    require(t.step(label,'Use the observed stock sit/stand binding and verify the native player pose.',
        {'pose':{'kind':'key','value':t.pose_key,'hold':.4,'description':'Press the installed sit/stand binding.'}},
        outcome,diagnostic_action='pose'),'native_sit_stand_pass')


def suite(t):
    t.session=actors.session_entry(t.fixture)['session'];oracle=Inventory(lab.ROOT,t.session,t.fixture['guid']).poll()
    t.clean_panels();state,_=t.observe('pose_fixture')
    if state.get('observer_version')!=74:raise RuntimeError('requires passive pose/binding observer74')
    t.bar_baseline=detail(t,'pose_layout');t.pose_baseline=pose(oracle)
    t.position_baseline=state.get('world_position');keys=t.bar_baseline['keys'].get('SITORSTAND')
    original_afk=afk(oracle)
    t.receipt['preflight']={'native_pose':t.pose_baseline,'native_afk':original_afk,
        'public_pose':t.bar_baseline['pose'],'position':t.position_baseline,'binding':keys};t.persist()
    if (t.pose_baseline['stand'] not in [0,1] or not keys or not t.position_baseline or
        len(t.position_baseline)!=4 or t.bar_baseline['pose'].get('speed')!=0 or
        t.bar_baseline['pose'].get('sheath')!=t.pose_baseline['sheath']+1):
        raise RuntimeError('requires a standing or seated idle owned fixture with public/native sheath agreement')
    t.pose_key=binding_key(keys[0]);original=resources(oracle);spells=known(t.fixture['guid'])
    actions=saved_actions(t.fixture['guid']);stats=native_state(oracle)
    t.receipt.update(native_session=t.session,baseline=original,native_persisted_spells=spells,
        native_actions=actions,native_state_baseline=stats,pose_baseline=t.pose_baseline,
        native_afk_baseline=original_afk,
        position_baseline=t.position_baseline,bar_baseline=t.bar_baseline,observed_pose_binding=keys,
        qualified_scope='Stock installed sit/stand binding on one standing or seated idle owned fixture. Native four-byte requests, one-byte state updates, stand-state fields, unchanged sheath/main bar/public position and exact rendered poses. Restore original pose and AFK status, health/power/stats, inventory/money and saved spell/action rows. Natural automatic AFK/sit packets and cleanup do not qualify binding actions. Other movement, emotes, combat, death, chairs and persistence remain open.');t.persist()
    try:
        for wanted in [1-t.pose_baseline['stand'],t.pose_baseline['stand']]:
            select(t,oracle,wanted,'movement.sit' if wanted else 'movement.stand')
    except Exception as error:
        t.receipt['execution_failure']=f'{type(error).__name__}: {error}';t.persist();raise
    finally:
        try:
            if pose(oracle)['stand']!=t.pose_baseline['stand']:
                select(t,oracle,t.pose_baseline['stand'],'movement.cleanup_pose')
            if afk(oracle)!=original_afk:
                t.receipt['afk_cleanup']={'source':'code_fixture_cleanup','input':'/afk',
                    'original':original_afk,'qualification':False};t.persist()
                t.execute({'kind':'chat','value':'/afk'})
                detail(t,'pose_afk_restored',lambda p:afk(oracle)==original_afk and
                    pose(oracle)['stand']==t.pose_baseline['stand'])
            final,_=t.observe('pose_restored');bar=detail(t,'pose_bar_restored')
            t.receipt['layout_restored']=(pose(oracle)==t.pose_baseline and
                final.get('world_position')==t.position_baseline and signature(bar)==signature(t.bar_baseline) and
                bar['pose']==t.bar_baseline['pose'] and afk(oracle)==original_afk);t.persist();t.clean_panels()
        finally:
            t.receipt.update(native_after=resources(oracle),native_pose_after=pose(oracle),
                native_afk_after=afk(oracle),
                native_state_after=native_state(oracle),native_actions_after=saved_actions(t.fixture['guid']),
                native_persisted_spells_after=known(t.fixture['guid']))
            t.receipt['native_resources_preserved']=(t.receipt['native_after']==original and
                restored_native_state(stats,t.receipt['native_state_after']) and
                t.receipt['native_actions_after']==actions and t.receipt['native_persisted_spells_after']==spells)
            t.persist()
    if not t.receipt['layout_restored'] or not t.receipt['native_resources_preserved']:
        raise RuntimeError('sit/stand did not restore original native/public state')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--actor',choices=['primary','scout'],required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    with actor(a.actor):
        t=Trial(a.output,controller='code')
        try:suite(t);t.receipt['completed']=True
        except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
        finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
