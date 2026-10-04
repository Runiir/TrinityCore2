"""Use stock spellbook tabs/pages/tooltips with passive and native checks."""
import argparse,hashlib,json,re,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_operations import controls,click_case,point
from .interaction_observation import read_current_page
from .interaction_macros import require
from .interaction_spellbook_recon import resources
from .observation.inventory import Inventory
from .observation.journal import latest
from .world.buffer import Reader


def detail(t,label,book_type=None):
    ready=None if book_type is None else lambda state:state.get('spellbook_probe',{}).get('book_type')==book_type
    state,frame=read_current_page(t,label,'spellbook',ready=ready)
    if state.get('observer_version',0)<61:raise RuntimeError('requires passive spellbook observer61')
    t.receipt.setdefault('spellbook_details',{})[label]={'state':state,'frame':frame,'input_sent':False};t.persist()
    return state['spellbook_probe']


def known(guid):
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT spell,active,disabled FROM client442_characters.character_spell WHERE guid=%s ORDER BY spell',(guid,))
        return [list(row) for row in q.fetchall()]


def wire_known(t,session):
    row=latest(lab.ROOT/'evidence/world_packets.jsonl',lambda r:r.get('session')==session and
        r.get('direction')=='from_native' and r.get('name')=='SMSG_SEND_KNOWN_SPELLS')
    if row is None:raise RuntimeError('native known-spell login packet is absent')
    body=bytes.fromhex(row['body']);reader=Reader(body);initial,count=reader.unpack('BH')
    if initial>1 or not 0<count<=16000:raise RuntimeError('native known-spell count is invalid')
    ids=[reader.unpack('Ih')[0] for _ in range(count)]
    cooldowns,=reader.unpack('H');history=[reader.unpack('IIHii') for _ in range(cooldowns)];reader.end()
    t.receipt['native_known_spell_packet']={'time':row['time'],'session':session,'name':row['name'],
        'body_sha256':hashlib.sha256(body).hexdigest(),'initial_login':initial,'ids':ids,'cooldowns':history}
    t.persist();return set(ids)


def checks(probe,learned):
    clean=lambda s:re.sub(r'\|c[0-9a-fA-F]{8}|\|r','',s or '').strip()
    rows=[r for r in probe['rows'] if r.get('slot')]
    tab=next((r for r in probe['tabs'] if r['index']==probe['skill_line']),None)
    current=probe.get('page');count=tab['count'] if tab else None
    expected=min(12,max(0,count-(current-1)*12)) if count is not None and current else None
    ordinary=[r for r in rows if r.get('kind')=='SPELL']
    return {'visible':probe['visible'],'spell_book':probe['book_type']==probe['book_types']['spell'],
        'selected_tab_checked':bool(tab and tab.get('checked')),
        'page_row_count':expected is not None and len(rows)==expected,
        'page_slots':bool(tab and current and expected is not None) and sorted(r['slot'] for r in rows)==
            list(range(tab['offset']+(current-1)*12+1,tab['offset']+(current-1)*12+1+expected)),
        'rendered_names':all(clean(r.get('shown_name'))==clean(r.get('name')) and bool(r.get('name')) for r in rows),
        'known_spell_identity':all(r.get('id') in learned and r.get('known') is True for r in ordinary),
        'public_slot_kind':all(r.get('kind')==r.get('api_kind') for r in rows)}


def navigate(t,learned,case_id,target,line=None,page=None,check_content=True):
    def outcome(b,a,s):
        probe=detail(t,case_id.replace('.','_'))
        valid=checks(probe,learned) if check_content else {'visible':probe['visible'],
            'spell_book':probe['book_type']==probe['book_types']['spell']}
        valid.update(selected=s,ui_clean=not a.get('lua_errors') and not a.get('blocked_actions'))
        if line is not None:valid['expected_skill_line']=probe['skill_line']==line
        if page is not None:valid['expected_page']=probe['page']==page
        return {'status':'spellbook_navigation_pass' if all(valid.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':valid,'probe':probe}}
    return click_case(t,case_id,'Use the observed stock spellbook control '+target+'.',
        lambda c:c['name']==target,outcome)


def hover(t,learned,passive):
    probe=detail(t,'before_'+('passive' if passive else 'active')+'_tooltip')
    row=next((r for r in probe['rows'] if r.get('kind')=='SPELL' and r.get('id') in learned and
        r.get('known') is True and r['passive']==passive),None)
    if row is None:raise RuntimeError('requires a native-known '+('passive' if passive else 'active')+' spell')
    control=next(c for c in controls(t) if c['name']==row['button'])
    def outcome(b,a,s):
        after=detail(t,'tooltip_'+('passive' if passive else 'active'));tip=after['tooltip']
        valid={'ordinary_hover':s=='hover','visible':tip['visible'],'owner':tip.get('owner')==row['button'],
            'spell_identity':tip.get('spell_id')==row['id'],'tooltip_lines':bool(tip['lines']),
            'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        return {'status':'spellbook_tooltip_pass' if all(valid.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':valid,'spell':row,'tooltip':tip}}
    require(t.step('spellbook.'+('passive_tooltip' if passive else 'spell_tooltip'),
        'Read the stock tooltip of a native-known spell.',{'hover':{'kind':'hover','value':point(control),
            'description':'Hover the observed '+row['name']+' spell button.'}},outcome,
        diagnostic_action='hover'),'spellbook_tooltip_pass')


def suite(t):
    session=actors.session_entry(t.fixture)['session'];oracle=Inventory(lab.ROOT,session,t.fixture['guid']).poll()
    t.clean_panels();original=resources(oracle);persisted=known(t.fixture['guid']);learned=wire_known(t,session);layout=None
    t.receipt.update(native_session=session,baseline=original,native_persisted_spells=persisted,
        qualified_scope='Owned human warrior stock General/class tabs, General next/previous page and active/passive tooltips only; casting, learning, professions and pet tabs remain open')
    t.persist()
    try:
        require(click_case(t,'spellbook.navigation.open','Open the observed stock spellbook microbutton.',
            lambda c:c['name']=='SpellbookMicroButton',lambda b,a,s:{'status':'spellbook_open_pass' if s and
                'SpellBookFrame' in a['panels'] else 'client_or_protocol_failure'},
            await_state=lambda a:'SpellBookFrame' in a['panels']),'spellbook_open_pass')
        layout=detail(t,'layout_baseline');t.receipt['book_layout_baseline']=layout;t.persist()
        require(navigate(t,learned,'spellbook.general_tab','SpellBookSkillLineTab1',line=1),'spellbook_navigation_pass')
        general=detail(t,'general_before_paging')
        if not general.get('page') or general['page']>=general.get('max_pages',0):raise RuntimeError('requires a following General page')
        require(navigate(t,learned,'spellbook.next_page','SpellBookNextPageButton',line=1,page=general['page']+1),'spellbook_navigation_pass')
        require(navigate(t,learned,'spellbook.previous_page','SpellBookPrevPageButton',line=1,page=general['page']),'spellbook_navigation_pass')
        hover(t,learned,False);hover(t,learned,True)
        for tab in layout['tabs']:
            if tab['index']>1 and not tab.get('hidden') and not tab.get('guild'):
                require(navigate(t,learned,'spellbook.class_tab.'+str(tab['index']),
                    'SpellBookSkillLineTab'+str(tab['index']),line=tab['index']),'spellbook_navigation_pass')
    finally:
        try:
            if layout:
                current=detail(t,'before_layout_restore')
                for line in [1,layout['skill_line']]:
                    if current['skill_line']!=line:
                        require(navigate(t,learned,'spellbook.layout_restore.line'+str(line),'SpellBookSkillLineTab'+str(line),
                            line=line,check_content=False),'spellbook_navigation_pass')
                        current=detail(t,'restoring_line'+str(line))
                    target=layout['pages'].get(str(line))
                    for attempt in range(3):
                        if current.get('page')==target:break
                        if not target or not current.get('page'):raise RuntimeError('cannot restore an absent original page')
                        step=-1 if current['page']>target else 1
                        require(navigate(t,learned,'spellbook.layout_restore.page'+str(line)+'_'+str(attempt),
                            'SpellBookPrevPageButton' if step<0 else 'SpellBookNextPageButton',line=line,
                            page=current['page']+step,check_content=False),'spellbook_navigation_pass')
                        current=detail(t,'restoring_page'+str(line)+'_'+str(attempt))
                    if current.get('page')!=target:raise RuntimeError('original spellbook page exceeded restoration bound')
                after=detail(t,'layout_restored')
                t.receipt['book_layout_restored']=all(after.get(k)==layout.get(k) for k in ['book_type','skill_line','pages','page'])
                if not t.receipt['book_layout_restored']:raise RuntimeError('original spellbook category/pages did not restore')
        finally:
            try:t.clean_panels()
            finally:
                t.receipt.update(native_after=resources(oracle),native_persisted_spells_after=known(t.fixture['guid']))
                t.receipt['native_resources_preserved']=t.receipt['native_after']==original and t.receipt['native_persisted_spells_after']==persisted
                t.persist()
                if not t.receipt['native_resources_preserved']:raise RuntimeError('spellbook trial changed native inventory/money/spells')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--actor',choices=['primary','scout'],required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    with actor(a.actor):
        t=Trial(a.output,controller='code')
        try:suite(t);t.receipt['completed']=True
        except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
        finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
