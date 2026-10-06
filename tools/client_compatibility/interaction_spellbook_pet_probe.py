"""Submit one stock native-known Summon Imp cast and retain its protocol outcome."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_operations import click_case,point
from .interaction_macros import require
from .interaction_spellbook_navigation import wire_known
from .interaction_spellbook_actions import locate
from .interaction_bridge_restoration import capture
from .interaction_bridge_deploy import shot
from .interaction_owned_class_fixture import prepared,origin_checks
from .observation.journal import Cursor
from .world.buffer import Reader
from .world.native_objects import guid as native_guid


def suite(t,path):
    old=prepared(t,path)
    if (t.fixture['character_name'],t.fixture['race'],t.fixture['class'],t.fixture['level'])!=('Harnesslock',1,9,1):
        raise RuntimeError('requires the prepared owned Warlock')
    session=actors.session_entry(t.fixture)['session'];t.clean_panels()
    learned=wire_known(t,session)
    if 688 not in learned:raise RuntimeError('natural Summon Imp is absent from native login spells')
    t.receipt.update(native_session=session,native_baseline=capture(t),
        qualified_scope='One stock Summon Imp compatibility probe only; no pet-tab or other operation qualification.')
    require(click_case(t,'spellbook.pet_probe.open','Open the observed stock spellbook.',
        lambda c:c['name']=='SpellbookMicroButton',lambda b,a,s:{'status':'spellbook_open_pass' if s and
            'SpellBookFrame' in a['panels'] else 'client_or_protocol_failure'}),'spellbook_open_pass')
    row,button=locate(t,learned,688)
    if row.get('name')!='Summon Imp' or row.get('known') is not True:raise RuntimeError('owned summon button differs')
    packets=Cursor(lab.ROOT/'evidence/world_packets.jsonl');events=Cursor(lab.ROOT/'logs/modern_world.jsonl')
    for _ in packets.poll():pass
    for _ in events.poll():pass
    started=time.time();t.receipt.update(summon_started_at=started,summon_spell=row,
        summon_input={'kind':'click','value':point(button),'button':3,'hold':1.2},
        before_summon=shot(t.out/'before_summon.png'));t.persist()
    t.io.click(*point(button),button=3,hold=1.2);time.sleep(16)
    rows=[r for r in packets.poll() if r.get('session')==session and r.get('time',0)>=started]
    outcomes=[]
    for r in rows:
        if r.get('name')=='SMSG_SPELL_GO' and r.get('direction')=='from_native':
            x=Reader(bytes.fromhex(r['body']));caster=native_guid(x);native_guid(x);counter,spell=x.unpack('Bi')
            if caster==t.fixture['guid'] and spell==688:outcomes.append({'time':r['time'],'caster':caster,'spell':spell,'counter':counter})
    safe={'CMSG_CAST_SPELL','SMSG_SPELL_START','SMSG_SPELL_GO','SMSG_CAST_FAILED','SMSG_PET_SPELLS'}
    retained=[{k:v for k,v in r.items() if k!='body' or r.get('name') in safe} for r in rows]
    diagnostics=[{k:r[k] for k in ['time','session','event','name','bytes','error','guid'] if k in r}
        for r in events.poll() if r.get('session')==session and r.get('time',0)>=started]
    t.receipt.update(protocol_rows=retained,native_summon_outcomes=outcomes,
        protocol_events=diagnostics,
        after_summon=shot(t.out/'after_summon.png'),origin_checks=origin_checks(old),
        phase='await_summon_outcome_review',requires_next_screen_review=True);t.persist()
    if not all(t.receipt['origin_checks'].values()):raise RuntimeError('pet probe changed the original parked scout')
    errors=[r['error'] for r in diagnostics if r.get('error')]
    if errors:raise RuntimeError('single summon compatibility failure: '+str(errors[:3]))
    if len(outcomes)!=1:raise RuntimeError('single stock summon lacks one attributable native completion')
    # Input-only completion requires a separate review and never qualifies the pet tab.
    t.receipt['completed']=True


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2)
        t.receipt.update(custom_script_permission='blocked_by_user',
            softTargetInteract={'original':'0','current_stock_disabled':'1','original_restored':False})
        try:suite(t,a.source)
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ['phase','completed','failure']}),flush=True)
