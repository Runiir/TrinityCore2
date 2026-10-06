"""Submit one stock native-known Summon Imp cast and retain its protocol outcome."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_operations import click_case,point,controls
from .interaction_macros import require
from .interaction_spellbook_navigation import wire_known,detail,navigate
from .interaction_observation import read_current_page
from .interaction_bridge_restoration import capture
from .interaction_bridge_deploy import shot
from .interaction_owned_class_fixture import prepared,origin_checks
from .observation.journal import Cursor
from .world.buffer import Reader
from .world.native_objects import guid as native_guid


def summon_button(t,learned,observe_only=False):
    probe=detail(t,'summon_flyout_tabs')
    tab=next((r for r in probe['tabs'] if r.get('name')=='Demonology' and not r.get('hidden')),None)
    if tab is None:raise RuntimeError('owned Demonology tab is absent')
    line=tab['index']
    require(navigate(t,learned,'spellbook.pet_probe.demonology','SpellBookSkillLineTab'+str(line),
        line=line,check_content=False),'spellbook_navigation_pass')
    for attempt in range(3):
        probe=detail(t,'summon_flyout_page'+str(attempt),line=line)
        if probe.get('page')==1:break
        if not 1<probe.get('page',0)<=3:raise RuntimeError('summon page exceeds its observed bound')
        require(navigate(t,learned,'spellbook.pet_probe.previous'+str(attempt),'SpellBookPrevPageButton',
            line=line,page=probe['page']-1,check_content=False),'spellbook_navigation_pass')
    row=next((r for r in probe['rows'] if r.get('kind')=='FLYOUT' and r.get('name')=='Summon Demon'),None)
    slots=(row or {}).get('flyout',{}).get('slots',[])
    if row is None or not any(r.get('id')==688 and r.get('known') is True for r in slots):
        raise RuntimeError('native-known Imp is absent from the public summon flyout')
    def ready(state):
        flyout=state.get('spellbook_probe',{}).get('flyout',{})
        return flyout.get('visible') and flyout.get('parent')==row['button'] and any(
            r.get('id')==688 and r.get('known') is True and r.get('enabled') for r in flyout.get('buttons',[]))
    def opened(b,a,s):
        state,frame=read_current_page(t,'summon_flyout_open','spellbook',ready=ready)
        probe=state['spellbook_probe']
        t.receipt.setdefault('spellbook_details',{})['summon_flyout_open']={'state':state,'frame':frame,'input_sent':False}
        valid=s=='open' and ready(state)
        return {'status':'summon_flyout_open_pass' if valid else 'client_or_protocol_failure','oracle':{'probe':probe}}
    candidates=[c for c in controls(t) if c['name']==row['button'] and c.get('enabled')]
    if len(candidates)!=1:raise RuntimeError('observed Summon Demon control is absent or ambiguous')
    require(t.step('spellbook.pet_probe.flyout','Open the observed stock Summon Demon flyout.',
        {'open':{'kind':'click','value':point(candidates[0]),'button':3,'hold':1.2,
            'description':'Right-click the observed stock Summon Demon row once.'}},
        opened,diagnostic_action='open'),'summon_flyout_open_pass')
    if observe_only:
        time.sleep(6)
        probe=detail(t,'summon_flyout_lifecycle')
        t.receipt.update(phase='flyout_lifecycle_observed',summon_input_sent=False,
            qualification_added=False,origin_checks=origin_checks(prepared(t,t.receipt['preparation_source'])))
        if not all(t.receipt['origin_checks'].values()):raise RuntimeError('flyout trace changed the parked scout')
        t.receipt['completed']=True
        return None
    probe=detail(t,'summon_flyout_before_cast');buttons=[r for r in probe['flyout']['buttons'] if
        r.get('id')==688 and r.get('known') is True and r.get('enabled') and r.get('name')=='Summon Imp']
    candidates=[c for c in controls(t) if c.get('spell_flyout') and c.get('spell_id')==688 and c.get('enabled')]
    if len(buttons)!=1 or len(candidates)!=1 or candidates[0]['name']!=buttons[0]['button']:
        raise RuntimeError('visible native-known Imp control is absent or ambiguous')
    return buttons[0],candidates[0]


def suite(t,path,observe_only=False):
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
    t.receipt['preparation_source']=str(path)
    result=summon_button(t,learned,observe_only)
    if observe_only:return
    row,button=result
    if row.get('name')!='Summon Imp' or row.get('known') is not True:raise RuntimeError('owned summon button differs')
    packets=Cursor(lab.ROOT/'evidence/world_packets.jsonl');events=Cursor(lab.ROOT/'logs/modern_world.jsonl')
    for _ in packets.poll():pass
    for _ in events.poll():pass
    started=time.time();t.receipt.update(summon_started_at=started,summon_spell=row,
        summon_input={'kind':'click','value':point(button),'button':1,'hold':1.2},
        before_summon=shot(t.out/'before_summon.png'));t.persist()
    t.io.click(*point(button),button=1,hold=1.2);time.sleep(16)
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
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--observe-flyout-only',action='store_true');a=p.parse_args()
    with actor('scout'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2)
        t.receipt.update(custom_script_permission='blocked_by_user',
            softTargetInteract={'original':'0','current_stock_disabled':'1','original_restored':False})
        try:suite(t,a.source,a.observe_flyout_only)
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ['phase','completed','failure']}),flush=True)
