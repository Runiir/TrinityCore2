"""Insert owned item or native-known spell links into chat without sending them."""
import argparse,json,re,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_keybindings_native import suite as native_suite
from .interaction_control_target import target
from .interaction_operations import point
from .interaction_macros import require
from .interaction_spellbook_navigation import detail as book_detail,known
from .observation.inventory import Inventory


def insert(t,kind,id,control):
    require(t.step('fixture.open_link_chat','Open a blank stock chat edit box without submitting a message.',
        {'open':{'kind':'key','value':'Return','description':'Open the stock chat edit box.'}},
        lambda b,a,s:{'status':'blank_chat_open' if a.get('chat_edit_open') and not a.get('chat_edit_text') else
            'client_or_protocol_failure'},diagnostic_action='open'),'blank_chat_open')
    def outcome(b,a,s):
        text=a.get('chat_edit_text') or '';match=re.search(r'\|H'+kind+r':(\d+)',text)
        checks={'ordinary_shift_click':s=='link','blank_before':bool(b.get('chat_edit_open')) and not b.get('chat_edit_text'),
            'chat_still_open':bool(a.get('chat_edit_open')),'requested_link':bool(match and int(match[1])==id),
            'rendered_label_markup':'|h[' in text and ']|h' in text,'no_item_cursor':not a.get('cursor_info'),
            'clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        return {'status':'stock_chat_link_pass' if all(checks.values()) else 'client_or_protocol_failure',
            'oracle':{'checks':checks,'kind':kind,'id':id,'pending_text':text,'message_submitted':False}}
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


def spell(t):
    learned={r[0] for r in known(t.fixture['guid']) if r[1:]==[1,0]}
    require(t.step('fixture.open_link_spellbook','Open the stock spellbook.',
        {'open':{'kind':'key','value':'p','description':'Open the installed stock spellbook.'}},
        lambda b,a,s:{'status':'link_spellbook_open' if 'SpellBookFrame' in a['panels'] else 'client_or_protocol_failure'},
        diagnostic_action='open'),'link_spellbook_open')
    layout=book_detail(t,'link_spellbook_before')
    if layout['book_type']!=layout['book_types']['spell']:raise RuntimeError('requires an original ordinary spellbook tab')
    row=next((r for r in layout['rows'] if r.get('kind')=='SPELL' and r.get('known') is True and
        r.get('id') in learned and r.get('passive') is False),None)
    if row is None:raise RuntimeError('requires a visible native-known active spell')
    t.receipt['link_spell_fixture']=row;t.persist()
    control=target(t,'native_known_link_spell',lambda c:c['name']==row['button'])
    insert(t,'spell',row['id'],control)
    t.execute({'kind':'key','value':'p'});after=book_detail(t,'link_spellbook_after')
    checks={k:after.get(k)==layout.get(k) for k in ['book_type','skill_line','pages','page']}
    t.receipt['link_spellbook_restoration']=checks;t.persist();t.clean_panels()
    if not all(checks.values()):raise RuntimeError('linking changed the original spellbook layout')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--kind',choices=['bag','spell'],required=True);a=p.parse_args()
    t=Trial(a.output,controller='code')
    try:native_suite(t,operations=bag if a.kind=='bag' else spell,preserve_settings=False);t.receipt['completed']=True
    except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
