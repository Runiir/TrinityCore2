"""Drag native-known spells and cast Battle Shout through stock spellbook inputs."""
import argparse,json,struct,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_operations import controls,point,click_case
from .interaction_macros import require
from .interaction_spellbook_navigation import detail,known,wire_known,navigate
from .interaction_spellbook_recon import resources
from .observation.inventory import Inventory
from .observation.journal import entries
from .world.buffer import Reader
from .world.native_objects import guid as native_guid


def saved_actions(guid):
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT spec,button,action,type FROM client442_characters.character_action WHERE guid=%s ORDER BY spec,button',(guid,))
        return [list(row) for row in q.fetchall()]


def action_writes(session,since,index,value):
    return [{'time':r['time'],'body':r['body']} for r in entries(lab.ROOT/'evidence/world_packets.jsonl')
        if r.get('session')==session and r.get('time',0)>=since and r.get('direction')=='to_native' and
        r.get('name')=='CMSG_SET_ACTION_BUTTON' and len(bytes.fromhex(r['body']))==5 and
        struct.unpack('<BI',bytes.fromhex(r['body']))==(index,value)]


def locate(t,learned,spell):
    if spell not in learned:raise RuntimeError('requested spell is absent from native known-spell packet')
    tabs=detail(t,'spell_search_tabs')['tabs']
    preferred='Fury' if spell==6673 else 'General'
    for tab in sorted(tabs,key=lambda row:row['name']!=preferred):
        if tab.get('hidden') or tab.get('guild'):continue
        require(navigate(t,learned,'spellbook.search.line'+str(tab['index']),
            'SpellBookSkillLineTab'+str(tab['index']),line=tab['index'],check_content=False),'spellbook_navigation_pass')
        for attempt in range(3):
            probe=detail(t,'spell_search_'+str(spell)+'_'+str(tab['index'])+'_'+str(attempt))
            row=next((r for r in probe['rows'] if r.get('id')==spell and r.get('known') is True and not r['passive']),None)
            if row:return row,next(c for c in controls(t) if c['name']==row['button'])
            if probe.get('page',0)>=probe.get('max_pages',0):break
            require(navigate(t,learned,'spellbook.search.next'+str(tab['index'])+'_'+str(attempt),
                'SpellBookNextPageButton',page=probe['page']+1,check_content=False),'spellbook_navigation_pass')
    raise RuntimeError('native-known active spell is absent from bounded stock pages')


def restore_bar(t,session,slot,destination,baseline):
    state,frame=t.observe('bar_before_restore')
    if state['action_probe'].get('kind'):
        since=time.time()
        t.receipt['bar_restore_input']={'before':frame,'kind':'shift_drag','start':destination,'end':[900,500]};t.persist()
        with t.io.hold_modifier('shift'):t.io.drag(destination,[900,500])
        deadline=time.monotonic()+16
        while True:
            state,frame=t.observe('bar_restore_wait')
            if not state['action_probe'].get('kind'):break
            if time.monotonic()>deadline:raise RuntimeError('action slot clear did not settle; refusing input replay')
            time.sleep(.2)
        writes=action_writes(session,since,slot-1,0)
        if not writes:raise RuntimeError('native action-slot clear packet is absent')
        t.receipt['native_action_clear']=writes
        # Removing an action can leave its icon on the cursor. Escape cancels it.
        t.execute({'kind':'key','value':'Escape'})
    lab.server_command('saveall');time.sleep(.5)
    t.receipt['native_actions_after']=saved_actions(t.fixture['guid'])
    t.receipt['native_actions_restored']=t.receipt['native_actions_after']==baseline;t.persist()
    if not t.receipt['native_actions_restored']:raise RuntimeError('saved action bars did not restore')


def cast(t,learned,session):
    row,button=locate(t,learned,6673);before,_=t.observe('cast_baseline')
    if 6673 in before.get('buffs',[]):raise RuntimeError('requires Battle Shout absent before the reversible cast')
    t.receipt['buffs_baseline']=before.get('buffs',[]);t.persist();since=time.time()
    def outcome(b,a,s):
        completed=[];failed=[]
        for r in entries(lab.ROOT/'evidence/world_packets.jsonl'):
            if r.get('session')!=session or r.get('time',0)<since or r.get('direction')!='from_native':continue
            if r.get('name')=='SMSG_SPELL_GO':
                reader=Reader(bytes.fromhex(r['body']));caster=native_guid(reader);native_guid(reader)
                count,spell=reader.unpack('Bi')
                if caster==t.fixture['guid'] and spell==6673:completed.append({'time':r['time'],'spell':spell,'caster':caster,'counter':count})
            elif r.get('name')=='SMSG_CAST_FAILED':failed.append(r)
        valid={'right_click':s=='cast','native_completion':bool(completed),'visible_buff':6673 in a.get('buffs',[]),
            'no_native_failure':not failed,'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        return {'status':'spellbook_cast_pass' if all(valid.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':valid,'spellbook_row':row,'native_completions':completed,'native_failures':failed}}
    try:
        require(t.step('spellbook.cast_spell','Cast native-known Battle Shout by right-clicking its stock spellbook button.',
            {'cast':{'kind':'click','value':point(button),'button':3,'description':'Right-click the observed Battle Shout.'}},
            outcome,diagnostic_action='cast',await_state=lambda s:6673 in s.get('buffs',[])),'spellbook_cast_pass')
    finally:
        # This is a normal gameplay slash command, never an addon API setter.
        t.execute({'kind':'chat','value':'/cancelaura Battle Shout'})
        deadline=time.monotonic()+16
        while True:
            state,frame=t.observe('buff_restore_wait')
            if 6673 not in state.get('buffs',[]):break
            if time.monotonic()>deadline:raise RuntimeError('Battle Shout cancellation did not settle')
            time.sleep(.2)
        t.receipt.update(buffs_restored=state.get('buffs',[])==t.receipt['buffs_baseline'],buff_restore_frame=frame);t.persist()
        if not t.receipt['buffs_restored']:raise RuntimeError('original buff set differs after cancellation')


def suite(t,with_cast):
    session=actors.session_entry(t.fixture)['session'];oracle=Inventory(lab.ROOT,session,t.fixture['guid']).poll()
    t.clean_panels();original=resources(oracle);persisted=known(t.fixture['guid']);learned=wire_known(t,session)
    lab.server_command('saveall');time.sleep(.5);actions=saved_actions(t.fixture['guid'])
    state,frame=t.observe('action_baseline');probe=state['action_probe'];slot=probe['slot']
    if probe.get('kind') or not 1<=slot<=144:raise RuntimeError('requires an empty valid observed action slot')
    destination=[round(probe['point'][0]/65535*1280),round(probe['point'][1]/65535*720)]
    t.receipt.update(baseline=original,native_persisted_spells=persisted,native_actions_before=actions,
        native_session=session,action_baseline={'probe':probe,'frame':frame},
        qualified_scope='Drag Auto Attack from a native-known stock book button to an empty visible bar slot, save and restore it. Optional right-click Battle Shout self-cast, native completion, public aura and normal cancellation. Other spells, classes and target modes remain open.')
    t.persist();layout=None
    try:
        require(click_case(t,'spellbook.actions.open','Open the stock spellbook.',lambda c:c['name']=='SpellbookMicroButton',
            lambda b,a,s:{'status':'spellbook_open_pass' if s and 'SpellBookFrame' in a['panels'] else 'client_or_protocol_failure'},
            await_state=lambda s:'SpellBookFrame' in s['panels']),'spellbook_open_pass')
        layout=detail(t,'action_book_layout');t.receipt['book_layout_baseline']=layout;t.persist()
        require(navigate(t,learned,'spellbook.actions.general','SpellBookSkillLineTab1',line=1,check_content=False),'spellbook_navigation_pass')
        row,source=locate(t,learned,6603);since=time.time()
        def outcome(b,a,s):
            writes=action_writes(session,since,slot-1,6603)
            lab.server_command('saveall');time.sleep(.5);saved=saved_actions(t.fixture['guid'])
            valid={'physical_drag':s=='drag','public_spell':a['action_probe'].get('kind')=='spell' and a['action_probe'].get('id')==6603,
                'native_write':bool(writes),'persisted_spell':any(r[1:]==[slot-1,6603,0] for r in saved)}
            return {'status':'spellbook_drag_pass' if all(valid.values()) else 'client_or_protocol_failure',
                'oracle':{'checks':valid,'source_row':row,'native_writes':writes,'native_saved_actions':saved}}
        require(t.step('spellbook.drag_to_bar','Drag Auto Attack from its observed stock spellbook button to the empty bar slot.',
            {'drag':{'kind':'drag','start':point(source),'end':destination,'description':'Drag the observed Auto Attack icon to the empty visible action button.'}},
            outcome,diagnostic_action='drag',await_state=lambda s:s['action_probe'].get('id')==6603),'spellbook_drag_pass')
        restore_bar(t,session,slot,destination,actions)
        if with_cast:cast(t,learned,session)
    finally:
        try:
            restore_bar(t,session,slot,destination,actions)
            if layout:
                current=detail(t,'before_action_layout_restore')
                for line,target in layout['pages'].items():
                    if current['pages'].get(line)==target:continue
                    require(navigate(t,learned,'spellbook.actions.restore_page_line'+line,'SpellBookSkillLineTab'+line,
                        line=int(line),check_content=False),'spellbook_navigation_pass')
                    for attempt in range(3):
                        current=detail(t,'restoring_action_page'+line+'_'+str(attempt))
                        if current.get('page')==target:break
                        step=-1 if current['page']>target else 1
                        require(navigate(t,learned,'spellbook.actions.restore_page'+line+'_'+str(attempt),
                            'SpellBookPrevPageButton' if step<0 else 'SpellBookNextPageButton',
                            page=current['page']+step,check_content=False),'spellbook_navigation_pass')
                    current=detail(t,'restored_action_page'+line)
                    if current.get('page')!=target:raise RuntimeError('original book page did not restore within its bound')
                if current['skill_line']!=layout['skill_line']:
                    require(navigate(t,learned,'spellbook.actions.restore_line','SpellBookSkillLineTab'+str(layout['skill_line']),
                        line=layout['skill_line'],check_content=False),'spellbook_navigation_pass')
                after=detail(t,'action_layout_restored')
                t.receipt['book_layout_restored']=all(after.get(k)==layout.get(k) for k in ['book_type','skill_line','pages','page'])
                if not t.receipt['book_layout_restored']:raise RuntimeError('stock book layout did not restore')
        finally:
            try:t.clean_panels()
            finally:
                t.receipt.update(native_after=resources(oracle),native_persisted_spells_after=known(t.fixture['guid']))
                t.receipt['native_resources_preserved']=t.receipt['native_after']==original and t.receipt['native_persisted_spells_after']==persisted
                t.persist()
                if not t.receipt['native_resources_preserved']:raise RuntimeError('spellbook action changed native inventory/money/spells')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--actor',choices=['primary','scout'],required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--with-cast',action='store_true');a=p.parse_args()
    with actor(a.actor):
        t=Trial(a.output,controller='code')
        try:suite(t,a.with_cast);t.receipt['completed']=True
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
        finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
