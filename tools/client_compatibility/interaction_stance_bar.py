"""Click stock warrior stance buttons with native form, cast and bar-slot oracles."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_social import actor
from .interaction_actionbar_pages import detail
from .interaction_operations import point
from .interaction_macros import require
from .interaction_spellbook_navigation import known
from .interaction_spellbook_actions import saved_actions
from .interaction_spellbook_recon import resources
from .interaction_archaeology_projects import dbc
from .observation.inventory import Inventory
from .observation.journal import entries
from .world.objects import INDEX
from .world.buffer import Reader
from .world.native_objects import guid as native_guid


def native_state(oracle):
    oracle.poll();fields=oracle.objects[oracle.guid]
    return {'form':(fields[INDEX['UNIT_FIELD_BYTES_2']]>>24)&255,
        'health':fields[INDEX['UNIT_FIELD_HEALTH']],
        'power':fields[INDEX['UNIT_FIELD_POWER1']], 'stats':oracle.character_stats()}


def completions(t,since,spell):
    rows=[]
    for row in entries(lab.ROOT/'evidence/world_packets.jsonl'):
        if (row.get('session')!=t.session or row.get('time',0)<since or
            row.get('direction')!='from_native' or row.get('name')!='SMSG_SPELL_GO'):continue
        reader=Reader(bytes.fromhex(row['body']));caster=native_guid(reader);native_guid(reader)
        count,identifier=reader.unpack('Bi')
        if caster==t.fixture['guid'] and identifier==spell:
            rows.append({'time':row['time'],'spell':identifier,'caster':caster,'counter':count})
    return rows


def slot_matches(t,probe):
    page=6+probe['form'];spec=probe['active_spec']-1
    expected={button:(action,kind) for group,button,action,kind in t.native_actions if group==spec}
    matches=[]
    for index,button in enumerate(probe['actions']):
        slot=(page-1)*12+index;entry=expected.get(slot);kind=button.get('kind')
        mapped={'spell':0,'item':128,'macro':64}.get(kind)
        if kind=='companion' and button.get('id') in t.native_mounts:mapped=0
        matches.append(button['slot']==slot+1 and (not kind if entry is None else
            button.get('id')==entry[0] and mapped==entry[1]))
    return probe['effective_page']==page and len(matches)==12 and all(matches)


def select(t,oracle,index,label):
    before=detail(t,label+'_before');button=next(r for r in before['forms'] if r['index']==index)
    if not all(button.get(k) is True for k in ['visible','enabled','castable']) or any(k not in button for k in ['x','y']):
        raise RuntimeError('requires an observed visible, enabled, castable stance button')
    spell=button['spell'];since=time.time()
    def outcome(b,a,s):
        probe=detail(t,label+'_value',lambda p:p['form']==index and
            all(r['active']==(r['index']==index) and r.get('checked')==(r['index']==index) for r in p['forms']))
        native=native_state(oracle);casts=completions(t,since,spell)
        checks={'ordinary_click':s=='stance','native_completion':bool(casts),
            'native_form':native['form']==t.contracts[spell]['form'],
            'zero_rage_preserved':native['power']==probe['power']==0,
            'visible_stance_bar':probe['frames'].get('StanceBarFrame') is True,
            'native_action_slots':slot_matches(t,probe),
            'native_action_rows_unchanged':saved_actions(t.fixture['guid'])==t.native_actions,
            'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        return {'status':'stock_stance_bar_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'public':probe,'native':native,'native_completions':casts}}
    require(t.step(label,'Select the observed stock stance button and verify its native form and bar.',
        {'stance':{'kind':'click','value':point(button),'description':'Click '+button['button']+'.'}},
        outcome,diagnostic_action='stance'),'stock_stance_bar_pass')


def suite(t):
    t.session=actors.session_entry(t.fixture)['session'];oracle=Inventory(lab.ROOT,t.session,t.fixture['guid']).poll()
    t.clean_panels();state,_=t.observe('stance_fixture')
    if state.get('observer_version',0)<72:raise RuntimeError('requires passive stance observer72')
    original=resources(oracle);spells=known(t.fixture['guid']);layout=detail(t,'stance_layout')
    native=native_state(oracle);t.native_actions=saved_actions(t.fixture['guid'])
    if layout['page']!=1 or layout['power_type']!=1 or layout['power']!=0 or native['power']!=0:
        raise RuntimeError('requires page1 and an idle zero-rage warrior')
    if [(r['index'],r['spell']) for r in layout['forms']]!=[(1,2457),(2,71),(3,2458)]:
        raise RuntimeError('requires all three installed warrior stance buttons')
    learned={r[0] for r in spells if r[1:]==[1,0]};effects,_=dbc('SpellEffect',27)
    t.contracts={r[24]:{'effect_id':r[0],'aura':r[3],'form':r[12]} for r in effects
        if r[24] in [2457,71,2458] and r[24] in learned and r[1]==6 and r[3]==36}
    if set(t.contracts)!={2457,71,2458} or native['form']!=t.contracts[layout['forms'][layout['form']-1]['spell']]['form']:
        raise RuntimeError('public stance lacks its exact native learned shapeshift contract')
    companions={r['id'] for r in layout['actions'] if r.get('kind')=='companion'}
    t.native_mounts={r[24] for r in effects if r[24] in companions and r[24] in learned and r[1]==6 and r[3]==78}
    if companions!=t.native_mounts or not slot_matches(t,layout):raise RuntimeError('initial bar does not match native action rows')
    t.receipt.update(baseline=original,native_persisted_spells=spells,native_actions=t.native_actions,
        native_state_baseline=native,layout_baseline=layout,native_stance_contracts=t.contracts,
        native_spell_effect_sha256=lab.sha256(lab.ROOT/'data/dbc/enUS/SpellEffect.dbc'),
        qualified_scope='Three stock stance buttons on one idle zero-rage warrior, ordinary clicks, native spell completions and shapeshift fields, active checkbox and all12 native action slots, then exact original stance/bar/resources restoration. Other classes, combat and rage retention remain open.');t.persist()
    try:
        for index in [r['index'] for r in layout['forms'] if r['index']!=layout['form']]+[layout['form']]:
            select(t,oracle,index,'actionbars.stance_bar.'+str(index))
    except Exception as error:
        t.receipt['execution_failure']=f'{type(error).__name__}: {error}';t.persist();raise
    finally:
        try:
            current=detail(t,'stance_restore_before')
            if current['form']!=layout['form']:select(t,oracle,layout['form'],'stance.cleanup_restore')
            after=detail(t,'stance_restored');t.receipt['layout_restored']=(after['form']==layout['form'] and
                [(r['slot'],r.get('kind'),r.get('id')) for r in after['actions']]==
                [(r['slot'],r.get('kind'),r.get('id')) for r in layout['actions']]);t.persist()
            if not t.receipt['layout_restored']:raise RuntimeError('original stance and bar did not restore')
            t.execute({'kind':'hover','value':[1000,360]});t.clean_panels()
        finally:
            t.receipt.update(native_after=resources(oracle),native_state_after=native_state(oracle),
                native_actions_after=saved_actions(t.fixture['guid']),native_persisted_spells_after=known(t.fixture['guid']))
            t.receipt['native_resources_preserved']=(t.receipt['native_after']==original and
                t.receipt['native_state_after']==native and t.receipt['native_actions_after']==t.native_actions and
                t.receipt['native_persisted_spells_after']==spells);t.persist()
    if not t.receipt['native_resources_preserved']:raise RuntimeError('stance trial did not restore native state')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--actor',choices=['primary','scout'],required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    with actor(a.actor):
        t=Trial(a.output,controller='code')
        try:suite(t);t.receipt['completed']=True
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
        finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
