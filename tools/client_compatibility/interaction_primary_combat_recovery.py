"""Clear one native-attested nearby aggressor with an ordinary owned ability."""
import argparse,copy,json,math,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_primary_throw_diagnostic import ThrowPresence,native_spell,SPELL
from .interaction_primary_combat_reentry import inventory,protected_snapshot
from .interaction_primary_melee_diagnostic import review
from .interaction_primary_range_diagnostic import restore
from .interaction_owned_class_fixture import character,saved,pets,SCRIPT_BOUNDARY
from .interaction_ground_movement import position
from .interaction_bridge_deploy import shot
from .interaction_combat_log import probe
from .interaction_pet_target import pair
from .pet_attack_capture_evidence import target_guid
from .world.native_objects import records
from .world.objects import INDEX


class Aggressors(ThrowPresence):
    def inspect_packet(self,p):
        super().inspect_packet(p)
        if p.get('name')!='SMSG_UPDATE_OBJECT' or p.get('direction')!='from_native':return
        for r in records(bytes.fromhex(p['body'])):
            if r.get('kind')==3 and r['guid']>>52==0xf13 and r['guid']>>32&0xfffff==2740:
                self.targets[r['guid']]={**r,'created_at':p['time']};self.removed.discard(r['guid'])


def guards(base):
    return {'position':position(1)==base['position'],'saved':saved(1)==base['saved'],
        'inventory':inventory(1)==base['inventory'],'pets':pets(1)==base['pets'],
        'money':character(1,1)['money']==base['money'],'protected':protected_snapshot()==base['protected']}


def source(t,path):
    d=json.loads(path.read_text())
    if (path.is_symlink() or path.name!='episode.json' or not path.resolve().is_relative_to(lab.ROOT/'evidence') or
        not d.get('finished_at') or d.get('actor')!=t.fixture or d.get('runtime')!=t.receipt['runtime'] or
        t.fixture['guid']!=1 or t.fixture['actor']!='primary'):
        raise RuntimeError('closed owned combat source identity differs')
    t.receipt['source']={'path':str(path.resolve()),'sha256':lab.sha256(path)};t.persist();return d


def stage(t,path):
    d=source(t,path)
    if d.get('failure')!='RuntimeError: interaction fixture is unsafe' or d.get('completed') is not False:
        raise RuntimeError('requires the failed idle entry, retained without acceptance')
    row=d['offline_source']['native'];base={k:d['offline_source'][k] for k in ('saved','pets','inventory')}
    base.update(money=row['money'],position=[row[k] for k in ('position_x','position_y','position_z','orientation','map')],
        protected=d['protected_baseline'])
    session=actors.session_entry(t.fixture)['session'];o=Aggressors(session,1,d['started_at']).poll()
    candidates=[r for g,r in o.targets.items() if g not in o.removed and g>>32&0xfffff==2740 and
        pair(r['fields'],'UNIT_FIELD_TARGET')==1 and r['fields'].get(INDEX['UNIT_FIELD_HEALTH'],0)>0 and
        math.dist(base['position'][:3],r['movement']['position'][:3])<5]
    if len(candidates)!=1 or not all(guards(base).values()):raise RuntimeError('requires one nearby native aggressor and preserved saved boundary')
    target=candidates[0]
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT entry,name FROM client442_world.creature_template WHERE entry=2740');name=list(q.fetchone() or ())
    if name!=[2740,'Shadowforge Darkweaver']:raise RuntimeError('native aggressor name differs')
    with t.bounded_combat_observation(60):
        before,frame=t.observe('aggressor_before_selection')
        if frame['movement']['health_percent']<90 or before['owner_melee']['active']:
            raise RuntimeError('requires healthy owned character with stopped melee')
        t.execute({'kind':'chat','value':'/targetexact Shadowforge Darkweaver'})
        state,frame=t.observe('aggressor_selected');o.poll()
    selected=o.target();checks=guards(base)
    checks.update(native_target=bool(selected and selected['guid']==target['guid']),
        native_aggressor=bool(selected and pair(selected['fields'],'UNIT_FIELD_TARGET')==1),
        public_target=state['target'].get('guid')==target_guid(target),
        public_health=state['target'].get('health')==target['fields'][INDEX['UNIT_FIELD_HEALTH']],
        public_name=state['target'].get('name')==name[1],ui_clean=not state.get('lua_errors') and not state.get('blocked_actions'))
    t.receipt.update(baseline=base,session=session,entry_started_at=d['started_at'],target=copy.deepcopy(selected),
        checks=checks,frame=shot(t.out/'review_ready.png'),phase='await_primary_hostile_review',qualification_added=False)
    if not all(checks.values()):raise RuntimeError('selected native aggressor differs')
    t.receipt['completed']=True


def run(t,path,review_path):
    d=source(t,path)
    if d.get('completed') is not True or d.get('phase')!='await_primary_hostile_review' or not all(d['checks'].values()):
        raise RuntimeError('requires whole native aggressor staging')
    base=d['baseline'];o=Aggressors(d['session'],1,d['entry_started_at']).poll()
    t.receipt.update(baseline=base,session=d['session'],qualification_added=False);t.persist()
    try:
        image=review(t,review_path,d,path,'primary_hostile_throw')
        if not all(guards(base).values()) or not o.target() or o.target()['guid']!=d['target']['guid']:
            raise RuntimeError('reviewed nearby aggressor or saved boundary changed')
        with lab.connection() as c,c.cursor() as q:
            q.execute('SELECT spell,active,disabled FROM client442_characters.character_spell WHERE guid=1 AND spell=57755')
            if q.fetchall()!=((57755,1,0),):raise RuntimeError('requires native-known Heroic Throw')
        with t.bounded_combat_observation(60):
            public_before=probe(t,'recovery_log_before')
            if not 0<=time.time()-image.stat().st_mtime<110:raise RuntimeError('aggressor review expired')
            since=time.time();t.execute({'kind':'chat','value':'/cast Heroic Throw'});time.sleep(1)
            state,frame=t.observe('recovery_after');public_after=probe(t,'recovery_log_after');o.poll()
        packets=[p for p in o.combat if p['time']>=since]
        requests=[p for p in packets if p['name']=='CMSG_CAST_SPELL' and p['direction']=='to_native']
        completed=[p for p in packets if p['name']=='SMSG_SPELL_GO' and p['direction']=='from_native' and native_spell(p)['spell']==SPELL]
        public_damage=[v for v in public_after.get('events',[]) if v.get('event')=='SPELL_DAMAGE' and v.get('sequence',0)>public_before['event_sequence']]
        t.receipt.update(packets=packets,frame=frame,public_combat_log_before=public_before,public_combat_log_after=public_after,
            native_target_after=o.targets.get(d['target']['guid']),phase='primary_hostile_recovery_captured',
            qualified_scope='One ordinary defensive ability against a native-attested aggressor; no interaction qualification.')
        t.persist()
        if len(requests)!=1 or not completed or not public_damage or frame['movement']['in_combat']:
            raise RuntimeError('ordinary defensive ability did not clear combat with public damage')
        t.receipt['completed']=True
    finally:restore(t,o,base)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['stage','run'])
    p.add_argument('--source',type=Path,required=True);p.add_argument('--review',type=Path)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.action=='run' and not a.review:p.error('requires one fresh reviewed native aggressor')
    with actor('primary'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2,chat_open_retry=True)
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:stage(t,a.source) if a.action=='stage' else run(t,a.source,a.review)
        except Exception as e:t.receipt.update(completed=False,failure=f'{type(e).__name__}: {e}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure','checks','restoration_checks')}),flush=True)
