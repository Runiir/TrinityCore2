"""Verify a disconnected reward trial's earned completion after owned reentry."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_quest_fixture import quest_state
from .interaction_trade import inventory


def verify(t,source):
    source=source.resolve()
    if not source.is_relative_to(lab.ROOT/'evidence') or source.name!='episode.json':
        raise ValueError('require a closed owned reward episode')
    run=json.loads(source.read_text());saved=run.get('retained_completed_quest',{})
    kills=[c for c in run.get('cases',[]) if c['id'].startswith('quests.complete_') and c['id'].endswith('_kill')]
    if (not run.get('finished_at') or run.get('completed') or run['actor']!=t.fixture or
        not run.get('completion_oracle',{}).get('passed') or saved.get('quest')!=52 or
        len(kills)!=13 or any(c['status']!='quest_progress_pass' for c in kills)):
        raise RuntimeError('requires thirteen attributable earned kills and a closed failed reward trial')
    identity=lambda p:{k:p[k] for k in ['pid','start_ticks']}
    if identity(lab.owned_process('worldserver'))!=identity(run['runtime']['worldserver']):
        raise RuntimeError('native worldserver lifetime changed')
    fixture_path=source.parent/'npc_fixture.json';restored_path=source.parent/'npc_restoration.json'
    fixture=json.loads(fixture_path.read_text());restored=json.loads(restored_path.read_text())
    if sorted(restored['temporary_teleports_removed'])!=sorted(r[0] for r in fixture['temporary_teleports']):
        raise RuntimeError('source lacks the completed fixture restoration')
    actors.session_entry(t.fixture);t.clean_panels();state,frame=t.observe('recovered_completion')
    current=quest_state(1);items=inventory()
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT position_x,position_y,position_z,orientation,map FROM client442_characters.characters WHERE guid=1')
        position=q.fetchone()
        q.execute('SELECT id FROM client442_world.game_tele WHERE name IN (%s,%s)',('TC442NpcRestore','TC442NpcService'))
        remaining=q.fetchall()
    expected=fixture['before'][3:]
    checks={'earned_quest_history_preserved':current==saved['quest_state'],
        'earned_inventory_money_preserved':json.loads(json.dumps(items))==saved['inventory_money'],
        'fixture_pose_restored':all(abs(a-b)<.01 for a,b in zip(position,expected)),
        'temporary_teleports_removed':not remaining,'public_owned_entry_verified':state['guid']==t.guid}
    t.receipt.update(completion_source={'file':str(source),'sha256':lab.sha256(source)},
        source_fixture={'file':str(fixture_path),'sha256':lab.sha256(fixture_path)},
        source_restoration={'file':str(restored_path),'sha256':lab.sha256(restored_path)},
        observed={'state':state,'frame':frame},native={'quests':current,'inventory_money':items,'position':position},
        restoration=checks)
    t.persist()
    if not all(checks.values()):raise RuntimeError('recovered completion or fixture differs from its saved evidence')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--source',type=Path,required=True);a=p.parse_args();t=Trial(a.output,controller='code')
    try:verify(t,a.source);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:
        t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
