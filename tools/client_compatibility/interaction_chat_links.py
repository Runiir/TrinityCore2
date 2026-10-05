"""Insert owned item or native-known spell links into chat without sending them."""
import argparse,json,re,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_keybindings_native import suite as native_suite
from .interaction_control_target import target,click
from .interaction_operations import point
from .interaction_macros import require
from .interaction_spellbook_navigation import detail as book_detail,known
from .interaction_stance_bar import restored_native_state
from .interaction_spellbook_actions import cast as normal_cast
from .observation.inventory import Inventory
from .observation.journal import entries
from .world.buffer import Reader
from .world.native_objects import guid as native_guid


def insert(t,kind,id,control):
    require(t.step('fixture.open_link_chat','Open a blank stock chat edit box without submitting a message.',
        {'open':{'kind':'key','value':'Return','description':'Open the stock chat edit box.'}},
        lambda b,a,s:{'status':'blank_chat_open' if a.get('chat_edit_open') and not a.get('chat_edit_text') else
            'client_or_protocol_failure'},diagnostic_action='open'),'blank_chat_open')
    session=actors.session_entry(t.fixture)['session'];since=time.time()
    def outcome(b,a,s):
        text=a.get('chat_edit_text') or '';match=re.search(r'\|H'+kind+r':(\d+)',text)
        requests=[];completions=[]
        for row in entries(lab.ROOT/'evidence/world_packets.jsonl'):
            if row.get('session')!=session or row.get('time',0)<since:continue
            if row.get('name')=='CMSG_CAST_SPELL' and row.get('direction') in {'from_client','to_native'}:
                requests.append({'time':row['time'],'direction':row['direction'],'name':row['name']})
            if row.get('name')=='SMSG_SPELL_GO' and row.get('direction')=='from_native':
                reader=Reader(bytes.fromhex(row['body']));caster=native_guid(reader);native_guid(reader)
                counter,spell=reader.unpack('Bi')
                if caster==t.fixture['guid']:completions.append({'time':row['time'],'spell':spell,'caster':caster})
        checks={'ordinary_shift_click':s=='link','blank_before':bool(b.get('chat_edit_open')) and not b.get('chat_edit_text'),
            'chat_still_open':bool(a.get('chat_edit_open')),'requested_link':bool(match and int(match[1])==id),
            'rendered_label_markup':'|h[' in text and ']|h' in text,'no_item_cursor':not a.get('cursor_info'),
            'clean':not a.get('lua_errors') and not a.get('blocked_actions'),
            'no_spell_cast_request':not requests,'no_owned_native_cast_completion':not completions}
        return {'status':'stock_chat_link_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'kind':kind,'id':id,'pending_text':text,'message_submitted':False,
                'session':session,'since':since,'cast_requests':requests,'native_cast_completions':completions}}
    require(t.step('ui_misc.'+kind+'_link','Insert the observed '+kind+' link into the pending chat edit box.',
        {'link':{'kind':'click','value':point(control),'modifiers':['shift'],
            'description':'Shift-left-click the observed owned '+kind+' control.'}},outcome,diagnostic_action='link'),
        'stock_chat_link_pass')
    t.clean_panels()


def bag(t):
    session=actors.session_entry(t.fixture)['session'];oracle=Inventory(lab.ROOT,session,t.fixture['guid']).poll()
    item=oracle.slot(0,10)
    if t.fixture['guid']!=1 or item['id']!=49778 or not item['guid']:
        raise RuntimeError('requires the exact owned spare Worn Greatsword backpack fixture')
    t.receipt['link_item_fixture']=item;t.persist()
    require(t.step('fixture.open_link_backpack','Open the owned backpack.',
        {'open':{'kind':'key','value':'b','description':'Open the backpack through its installed stock binding.'}},
        lambda b,a,s:{'status':'link_bag_open' if 0 in a.get('bags',[]) and any(x['bag']==0 and x['slot']==10 and
            x['id']==item['id'] and not x['locked'] for x in a.get('bag_items',[])) else 'client_or_protocol_failure'},
        diagnostic_action='open'),'link_bag_open')
    control=target(t,'owned_link_item',lambda c:c['kind']=='Button' and c.get('bag_id')==0 and c.get('bag_slot')==10)
    insert(t,'item',item['id'],control)
    if oracle.slot(0,10)!=item:raise RuntimeError('linking changed the native owned item')


def spell(t,with_cast=False):
    learned={r[0] for r in known(t.fixture['guid']) if r[1:]==[1,0]}
    require(t.step('fixture.open_link_spellbook','Open the stock spellbook.',
        {'open':{'kind':'key','value':'p','description':'Open the installed stock spellbook.'}},
        lambda b,a,s:{'status':'link_spellbook_open' if 'SpellBookFrame' in a['panels'] else 'client_or_protocol_failure'},
        diagnostic_action='open'),'link_spellbook_open')
    layout=book_detail(t,'link_spellbook_before')
    if layout['book_type']!=layout['book_types']['spell']:raise RuntimeError('requires an original ordinary spellbook tab')
    if layout.get('chat_link_dispatch') is not True:raise RuntimeError('requires the installed secure stock chat-link dispatch repair')
    current=layout
    try:
        row=next((r for r in current['rows'] if r.get('kind')=='SPELL' and r.get('known') is True and
            r.get('id') in learned and r.get('passive') is False),None)
        if row is None:
            tab=next((r for r in layout['tabs'] if r['name']=='Fury' and not r.get('hidden') and
                not r.get('guild')),None)
            if tab is None:raise RuntimeError('requires an observed Fury tab for the owned warrior fixture')
            select_line(t,'fixture.link_class_tab',tab['index'])
            current=book_detail(t,'link_class_spells',line=tab['index'])
            row=next((r for r in current['rows'] if r.get('kind')=='SPELL' and r.get('known') is True and
                r.get('id') in learned and r.get('passive') is False),None)
        if row is None:raise RuntimeError('requires a visible native-known active spell')
        t.receipt['link_spell_fixture']=row;t.persist()
        control=target(t,'native_known_link_spell',lambda c:c['name']==row['button'])
        insert(t,'spell',row['id'],control)
        if with_cast:
            t.execute({'kind':'key','value':'p'})
            normal_cast(t,learned,actors.session_entry(t.fixture)['session'])
    finally:
        state,_=t.observe('link_book_cleanup')
        if 'SpellBookFrame' not in state['panels']:t.execute({'kind':'key','value':'p'})
        current=book_detail(t,'link_book_cleanup_layout')
        if current['skill_line']!=layout['skill_line']:select_line(t,'fixture.restore_link_book_tab',layout['skill_line'])
        after=book_detail(t,'link_spellbook_after',line=layout['skill_line'])
        checks={k:after.get(k)==layout.get(k) for k in ['book_type','skill_line','pages','page']}
        t.receipt['link_spellbook_restoration']=checks;t.persist();t.clean_panels()
        if not all(checks.values()):raise RuntimeError('linking changed the original spellbook layout')


def select_line(t,label,index):
    require(click(t,label,'Select the observed stock spellbook tab.',
        lambda c:c['name']=='SpellBookSkillLineTab'+str(index),
        lambda b,a,s:{'status':'link_book_tab_pass' if s and book_detail(t,label,line=index)['skill_line']==index
            else 'client_or_protocol_failure'}),'link_book_tab_pass')


def achievement(t):
    from .interaction_achievements import detail,saved,restore_layout
    from .interaction_archaeology_projects import dbc
    original=saved(t.fixture['guid']);layout=None
    def opened(label):
        require(click(t,label,'Open the stock achievement journal.',lambda c:c['name']=='AchievementMicroButton',
            lambda b,a,s:{'status':'link_achievement_open' if s and 'AchievementFrame' in a['panels'] else
                'client_or_protocol_failure'}),'link_achievement_open')
    try:
        opened('fixture.open_link_achievements');layout=detail(t,'link_achievement_original')
        if layout['category']!=92:
            category=next((r for r in layout['categories'] if r['id']==92),None)
            if category is None:raise RuntimeError('requires the observed General achievement category')
            require(click(t,'fixture.link_achievement_category','Open the observed General category.',
                lambda c:c['name']==category['button'],lambda b,a,s:{'status':'link_achievement_category' if s and
                    detail(t,'link_achievement_general',lambda p:p['category']==92)['category']==92 else
                    'client_or_protocol_failure'}),'link_achievement_category')
        current=detail(t,'link_achievement_rows',lambda p:bool(p['rows']))
        rows,text=dbc('Achievement',14);catalog={r[0]:text(r[4]) for r in rows}
        row=next((r for r in current['rows'] if catalog.get(r['id'])==r['name']==r['shown_name']),None)
        if row is None:raise RuntimeError('requires an observed native-catalog achievement row')
        t.receipt['link_achievement_fixture']={'row':row,'native_before':original,
            'catalog_sha256':lab.sha256(lab.ROOT/'data/dbc/enUS/Achievement.dbc')};t.persist()
        control=target(t,'native_achievement_link',lambda c:c['name']==row['button'])
        insert(t,'achievement',row['id'],control)
    finally:
        if layout:
            state,_=t.observe('link_achievement_cleanup')
            if 'AchievementFrame' not in state['panels']:opened('fixture.reopen_link_achievements')
            restore_layout(t,layout);t.clean_panels()
        unchanged=saved(t.fixture['guid'])==original
        t.receipt['link_native_achievements_preserved']=unchanged;t.persist()
        if not unchanged:raise RuntimeError('achievement linking changed native achievements or criteria')


def recovered(t,source):
    source=source.resolve()
    if not source.is_relative_to(lab.ROOT/'evidence') or source.name!='episode.json':
        raise ValueError('require the owned failed spell-link episode')
    old=json.loads(source.read_text())
    if (not old.get('finished_at') or old.get('completed') or old['actor']!=t.fixture or
            old['runtime']!=t.receipt['runtime'] or old.get('failure')!='RuntimeError: native binding fixture restoration differs' or
            not any(c['id'] in {'ui_misc.spell_link','spellbook.cast_spell'} and c['status']=='client_or_protocol_failure'
                for c in old['cases'])):
        raise RuntimeError('recovery requires the exact closed failed spell-link source and unchanged runtime')
    before=json.loads(json.dumps(t.receipt['native_baseline']));expected=old['native_baseline']
    checks={k:before[k]==expected[k] for k in expected if k!='stats'}
    checks['stats']=restored_native_state(expected['stats'],before['stats'])
    t.receipt['original_link_fixture_recovered']={'source':str(source),'sha256':lab.sha256(source),
        'checks':checks,'method':'read-only verification of the original native fixture after self-buff expiry or a blocked cast'};t.persist()
    if not all(checks.values()):raise RuntimeError('original pre-link native fixture has not returned')
    layout=old['spellbook_details']['link_spellbook_before']['state']['spellbook_probe']
    state,_=t.observe('recovery_book_before')
    if 'SpellBookFrame' not in state['panels']:t.execute({'kind':'key','value':'p'})
    current=book_detail(t,'recovery_book_layout')
    if current['skill_line']!=layout['skill_line']:select_line(t,'fixture.restore_failed_link_book_tab',layout['skill_line'])
    after=book_detail(t,'recovered_link_book',line=layout['skill_line'])
    restored={k:after.get(k)==layout.get(k) for k in ['book_type','skill_line','pages','page']}
    t.receipt['link_spellbook_restoration']=restored;t.persist();t.clean_panels()
    if not all(restored.values()):raise RuntimeError('failed source spellbook layout has not restored')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--kind',choices=['bag','spell','achievement'],required=True)
    p.add_argument('--recover-source',type=Path)
    p.add_argument('--normal-cast',action='store_true',help='Also verify the unchanged ordinary right-click cast and cancel its self-buff')
    a=p.parse_args()
    if a.recover_source and a.kind!='spell':p.error('recovery applies only to the closed spell-link source')
    if a.normal_cast and (a.kind!='spell' or a.recover_source):p.error('ordinary cast regression requires a fresh spell trial')
    t=Trial(a.output,controller='code')
    try:
        operation=(lambda t:recovered(t,a.recover_source)) if a.recover_source else {
            'bag':bag,'spell':lambda t:spell(t,a.normal_cast),'achievement':achievement}[a.kind]
        native_suite(t,operations=operation,preserve_settings=False);t.receipt['completed']=True
    except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
