"""Earn positive and negative standing through one ordinary Bloodsail Raider kill."""
import argparse,json,math,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_reputation import open_panel,catalog,native_state,native_catalog,standing_oracle
from .interaction_trade import inventory
from .interaction_macros import require
from .reputation_combat_fixture import CombatFixture
from .observation.transport import Observer
from .observation.journal import entries
from .travel_inputs import face
from .world.buffer import Reader


def standing_packets(session,started):
    result=[]
    for p in entries(lab.ROOT/'evidence/world_packets.jsonl'):
        if p.get('session')!=session or p.get('time',0)<started or p.get('name')!='SMSG_SET_FACTION_STANDING':continue
        r=Reader(bytes.fromhex(p['body']))
        if p['direction']=='from_native':
            bonus,visual,count=r.unpack('fBI');rows=[r.unpack('Ii') for _ in range(count)]
        elif p['direction']=='to_client':
            bonus,count=r.unpack('fI');rows=[r.unpack('iii') for _ in range(count)];visual=r.bits(1);r.align()
        else:continue
        r.end();result.append({'direction':p['direction'],'time':p['time'],'bonus':bonus,'visual':visual,'rows':rows})
    return result


def suite(t):
    session=actors.session_entry(t.fixture)['session'];t.clean_panels()
    baseline,items=native_state(),inventory();native_before=native_catalog(baseline)
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT creature_id,RewOnKillRepFaction1,RewOnKillRepFaction2,RewOnKillRepValue1,RewOnKillRepValue2 '
            'FROM client442_world.creature_onkill_reward WHERE creature_id=1561');reward=q.fetchone()
    if reward!=(1561,21,87,5,-25):raise RuntimeError('registered positive/negative native reward changed')
    t.receipt.update(baseline={'native':baseline,'inventory_money':items},reward_contract=reward);t.persist()
    fixture=CombatFixture(t);earned=None
    try:
        with t.bounded_combat_observation(60):
            fixture.prepare()
            require(t.step('reputation.combat_target','Target the nearby Bloodsail Raider.',
                {'target':{'kind':'chat','value':'/targetexact Bloodsail Raider','description':'Target the existing creature by its visible name.'}},
                lambda b,a,s:{'status':'reputation_target_pass' if s=='target' and a.get('target',{}).get('name')=='Bloodsail Raider'
                    and a['target'].get('visible') and a['target'].get('health',0)>0 else 'client_or_protocol_failure',
                    'oracle':{'target':a.get('target')}},diagnostic_action='target'),'reputation_target_pass')
            observer=Observer(guid=1);facts=observer.poll();unit=facts.get('selected_unit')
            if not unit or unit['guid']>>32&0xfffff!=1561 or unit['health']!=unit['max_health']:
                raise RuntimeError('requires the observed undamaged Bloodsail Raider')
            distance=math.dist(facts['position'][:3],unit['position'][:3])
            if distance>10 or abs(facts['position'][2]-unit['position'][2])>3:
                raise RuntimeError('target is outside the bounded ground approach')
            keys=face(t.io,observer,unit['position'])
            if distance>3:
                hold=min(1,(distance-2.5)/7);t.io.key('w',hold=hold);keys.append({'key':'w','hold':hold})
            t.receipt['ordinary_approach']={'facts':facts,'target':unit,'physical_keys':keys};t.persist()
            started=time.time()
            def killed(b,a,s):
                nonlocal earned
                deadline=time.monotonic()+12;samples=[]
                while True:
                    earned=native_state();now=native_catalog(earned);after=observer.poll().get('selected_unit')
                    target=a.get('target',{});samples.append({'target':target,'native_target':after,
                        'gain':now[21]['value']-native_before[21]['value'],'loss':now[87]['value']-native_before[87]['value']})
                    done=now[21]['value']>native_before[21]['value'] and now[87]['value']<native_before[87]['value']
                    dead=after and after['guid']==unit['guid'] and after['health']==0 and target.get('health')==0
                    if done and dead or time.monotonic()>deadline:break
                    time.sleep(.3);a,frame=t.observe('reputation_combat_settling_'+str(len(samples)))
                packets=standing_packets(session,started)
                pairs={direction:{row[0]:row[1] for p in packets if p['direction']==direction for row in p['rows']}
                    for direction in ['from_native','to_client']}
                matched=all(all(pairs[d].get(now[id]['index'])==now[id]['offset'] for d in pairs) for id in [21,87])
                passed=s=='attack' and done and dead and matched
                oracle={'samples':samples,'packets':packets,'native_after':earned,'native_public_packets_agree':matched,
                    'ordinary_melee_only':True,'passed':bool(passed)};t.receipt['kill_oracle']=oracle;t.persist()
                return {'status':'reputation_kill_pass' if passed else 'client_or_protocol_failure','oracle':oracle}
            require(t.step('reputation.combat_kill','Kill the targeted Raider using ordinary melee attacks.',
                {'attack':{'kind':'chat','value':'/startattack','description':'Start normal auto attacks on the selected creature.'}},
                killed,diagnostic_action='attack'),'reputation_kill_pass')
    finally:
        fixture.restore()
        t.execute({'kind':'chat','value':'/stopattack'});t.execute({'kind':'chat','value':'/cleartarget'})
        t.clean_panels();t.receipt['restoration']={'inventory_money_unchanged':inventory()==items,
            'native_earned_standings_retained':native_state(),'pose_restored':bool(fixture.rows and
                t.receipt.get('combat_fixture',{}).get('restoration',{}).get('teleports_removed'))};t.persist()
        if not t.receipt['restoration']['inventory_money_unchanged']:raise RuntimeError('combat altered inventory or money')
    open_panel(t);public=catalog(t,'earned_reputations');after=native_state();native=native_catalog(after)
    t.receipt['standing_oracles']=standing_oracle(public,native)
    by_id={r['id']:r for r in public['rows']}
    checks={str(id):id in by_id and by_id[id]['value']==native[id]['value'] for id in [21,87]}
    t.receipt['earned_public_oracle']={'public':public,'native':after,'checks':checks,'passed':all(checks.values())};t.persist()
    t.clean_panels()
    if not all(checks.values()):raise RuntimeError('earned positive/negative factions are not visible with exact native standings')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    t=Trial(a.output,controller='code')
    try:suite(t);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:
        t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
