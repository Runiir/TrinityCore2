"""Submit one reviewed Heroic Throw and retain each native/client outcome boundary."""
import argparse,json,struct,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_primary_range_diagnostic import RangePresence,source,restore,static_position
from .interaction_primary_melee_diagnostic import review
from .interaction_primary_combat_reentry import protected_snapshot
from .interaction_ground_movement import position
from .interaction_owned_class_fixture import SCRIPT_BOUNDARY
from .world.native_objects import guid

SPELL=57755
CAST_NAMES={'SMSG_SPELL_START','SMSG_SPELL_GO','SMSG_CAST_FAILED','SMSG_SPELL_FAILURE',
    'SMSG_SPELL_FAILED_OTHER','SMSG_SPELL_PREPARE','SMSG_SPELLNONMELEEDAMAGELOG',
    'SMSG_SPELL_NON_MELEE_DAMAGE_LOG','SMSG_SPELL_COOLDOWN','SMSG_COOLDOWN_EVENT'}


class ThrowPresence(RangePresence):
    def inspect_packet(self,p):
        super().inspect_packet(p)
        if p.get('name') in CAST_NAMES:
            if len(self.combat)>=256:raise RuntimeError('throw packet bound exceeded')
            self.combat.append(p)


def native_spell(p):
    from .world.buffer import Reader
    r=Reader(bytes.fromhex(p['body']))
    if p['name']=='CMSG_CAST_SPELL':
        count,spell=r.unpack('Bi');return {'counter':count,'spell':spell}
    if p['name'] in ('SMSG_SPELL_START','SMSG_SPELL_GO'):
        caster,unit=guid(r),guid(r);count,spell=r.unpack('Bi')
        return {'caster':caster,'unit':unit,'counter':count,'spell':spell}
    return None


def run(t,path,review_path):
    d=source(t,path,'await_primary_range_review')
    if len(d.get('checks',{}))!=13 or not all(d['checks'].values()):raise RuntimeError('current target staging incomplete')
    o=ThrowPresence(d['session'],1,d['entry_started_at']).poll();base=d['baseline'];target=d['target']
    t.receipt.update(baseline=base,session=d['session'],qualification_added=False,spell=SPELL);t.persist()
    try:
        image=review(t,review_path,d,path,'primary_throw')
        if (position(1)!=base['position'] or not o.target() or o.target()['guid']!=target['guid'] or
            protected_snapshot()!=base['protected'] or static_position(o.target())!=d['static_position_authority'] or
            not 10<d['distance_metres']<25):raise RuntimeError('reviewed native target or saved pose changed')
        with lab.connection() as c,c.cursor() as q:
            q.execute('SELECT spell,active,disabled FROM client442_characters.character_spell WHERE guid=1 AND spell=%s',(SPELL,))
            known=q.fetchall();q.execute('SELECT spell,time FROM client442_characters.character_spell_cooldown WHERE guid=1 AND spell=%s',(SPELL,))
            cooldown=q.fetchall()
        if known!=((SPELL,1,0),) or any(row[1]>time.time() for row in cooldown):
            raise RuntimeError('requires native-known Heroic Throw with no saved active cooldown')
        t.receipt.update(native_known_spell=[list(v) for v in known],native_saved_cooldown=[list(v) for v in cooldown]);t.persist()
        before,_=t.observe('throw_before')
        if before.get('errors'):raise RuntimeError('requires fresh passive error history')
        if not 0<=time.time()-image.stat().st_mtime<110:raise RuntimeError('throw review expired')
        since=time.time()
        with t.bounded_combat_observation(60):
            t.execute({'kind':'chat','value':'/cast Heroic Throw'});time.sleep(1)
            after,frame=t.observe('throw_after');o.poll()
        packets=[p for p in o.combat if p['time']>=since]
        requests=[p for p in packets if p['name']=='CMSG_CAST_SPELL' and p['direction']=='from_client']
        native=[p for p in packets if p['name']=='CMSG_CAST_SPELL' and p['direction']=='to_native']
        completed=[p for p in packets if p['name']=='SMSG_SPELL_GO' and p['direction']=='from_native' and native_spell(p)['spell']==SPELL]
        errors=[v for v in (after.get('errors') or []) if v not in (before.get('errors') or [])]
        from .observation.journal import Cursor
        rejected=[p for p in Cursor(lab.ROOT/'logs/modern_world.jsonl').poll() if p.get('session')==d['session'] and
            p.get('time',0)>=since and p.get('event')=='cast_translation_rejected']
        t.receipt.update(packets=packets,public_errors=errors,bridge_rejections=rejected,frame=frame,
            native_completions=completed,request_counts={'modern':len(requests),'native':len(native)},
            health_after=after.get('target'),phase='primary_throw_outcome_captured',
            qualified_scope='One ordinary targeted damage ability diagnosis. No combat interaction is admitted by capture alone.')
        t.persist()
        if len(requests)!=1 or len(native)!=1 or native_spell(native[0])['spell']!=SPELL or not completed:
            raise RuntimeError('targeted Heroic Throw lacks one exact native request and completion')
        t.receipt['completed']=True
    finally:restore(t,o,base)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--review',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    with actor('primary'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2,chat_open_retry=True)
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:run(t,a.source,a.review)
        except Exception as e:t.receipt.update(completed=False,failure=f'{type(e).__name__}: {e}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure','request_counts','bridge_rejections','restoration_checks')}),flush=True)
