"""Require a real native spell outcome, public combat event and stock log text."""
import argparse,json,time
from pathlib import Path
from . import actors
from .interaction_trial import Trial
from .interaction_keybindings_native import suite as native_suite
from .interaction_chat_window import detail as chat_detail,menu,option
from .interaction_chat_settings import signature
from .interaction_spellbook_navigation import detail as book_detail,known
from .interaction_spellbook_actions import cast
from .interaction_chat_links import select_line
from .interaction_control_target import click
from .interaction_observation import read_page
from .interaction_operations import command,controls
from .interaction_macros import require


def probe(t,label):
    try:
        state,frame=read_page(t,label,'combat_log','/tcui combat_log')
        result=state['combat_log_probe']
        t.receipt.setdefault('combat_log_details',{})[label]={'public':result,'frame':frame};t.persist()
        return result
    finally:command(t,'/tcui state')


def settings_recon(t,message_types=False):
    original=chat_detail(t,'combat_settings_original_chat');before=probe(t,'combat_settings_original')
    if original['selected']!=1 or not before['saved_settings']['available']:
        raise RuntimeError('requires original General selection and public saved combat settings')
    t.receipt['combat_settings_baseline']=before;t.persist()
    try:
        menu(t,2,'fixture.combat_settings_menu')
        require(option(t,'fixture.open_combat_settings','Settings',lambda b,a,s:{'status':'combat_settings_open'
            if s and 'ChatConfigFrame' in a['panels'] else 'client_or_protocol_failure'}),'combat_settings_open')
        if message_types:
            require(click(t,'fixture.combat_message_types','Inspect the observed stock Message Types tab.',lambda c:
                c['name']=='CombatConfigTab2' and c['text']=='Message Types',lambda b,a,s:{'status':'combat_message_types_visible'
                if s and 'ChatConfigFrame' in a['panels'] else 'client_or_protocol_failure'}),'combat_message_types_visible')
        rows=controls(t);state,frame=t.observe('combat_settings_rendered');current=probe(t,'combat_settings_open')
        t.receipt['combat_settings_recon']={'controls':rows,'frame':frame,'public':current};t.persist()
    finally:
        t.clean_panels();current=chat_detail(t,'combat_settings_cleanup_chat')
        if current['selected']!=original['selected']:
            require(click(t,'fixture.restore_general_after_combat_settings','Restore the original General tab.',lambda c:
                c['name']=='ChatFrame1Tab' and c['text']=='General',lambda b,a,s:{'status':'chat_selection_restored'
                if s and chat_detail(t,'combat_settings_restored_selection')['selected']==1 else
                'client_or_protocol_failure'}),'chat_selection_restored')
        after=probe(t,'combat_settings_restored');chat=chat_detail(t,'combat_settings_restored_chat')
        checks={'saved_settings_fingerprint':after['saved_settings']==before['saved_settings'],
            'original_chat_settings':signature(original)==signature(chat),'settings_closed':not chat['settings_visible']}
        t.receipt['combat_settings_restoration']={'checks':checks,'public':after};t.persist()
        if not all(checks.values()):raise RuntimeError('original combat preferences or chat settings differ')


def run(t):
    original=chat_detail(t,'combat_log_original_chat');baseline=probe(t,'combat_log_original')
    if original['selected']!=1 or not baseline['event_registered'] or not baseline['text_reader_available']:
        raise RuntimeError('requires original General selection and public stock combat-log readers')
    learned={r[0] for r in known(t.fixture['guid']) if r[1:]==[1,0]}
    t.receipt['combat_log_baseline']=baseline;t.receipt['chat_baseline']=original;t.persist()
    try:
        require(t.step('fixture.open_combat_log_spellbook','Open the stock spellbook for the native-known log fixture.',
            {'open':{'kind':'key','value':'p','description':'Open the ordinary stock spellbook.'}},lambda b,a,s:
            {'status':'stock_spellbook_open' if s=='open' and 'SpellBookFrame' in a['panels'] else
            'client_or_protocol_failure'},diagnostic_action='open'),'stock_spellbook_open')
        layout=book_detail(t,'combat_log_original_book')
        if layout['page']!=1 or layout['book_type']!=layout['book_types']['spell']:
            raise RuntimeError('requires the original ordinary page1 spellbook layout')
        t.receipt['combat_log_book_baseline']=layout;t.persist()
        try:cast(t,learned,actors.session_entry(t.fixture)['session'])
        finally:
            state,_=t.observe('combat_log_book_cleanup')
            if 'SpellBookFrame' not in state['panels']:t.execute({'kind':'key','value':'p'})
            current=book_detail(t,'combat_log_current_book')
            if current['skill_line']!=layout['skill_line']:select_line(t,'fixture.restore_combat_log_book_tab',layout['skill_line'])
            after=book_detail(t,'combat_log_restored_book',line=layout['skill_line'])
            checks={k:after.get(k)==layout.get(k) for k in ['book_type','skill_line','pages','page']}
            t.receipt['combat_log_book_restoration']=checks;t.persist();t.clean_panels()
            if not all(checks.values()):raise RuntimeError('original spellbook layout differs after real cast')
        def logged(b,a,s):
            result=probe(t,'combat_log_real_event');chat=chat_detail(t,'combat_log_selected_chat')
            events=[e for e in result['events'] if e['sequence']>baseline['event_sequence'] and
                e['source_guid']==t.guid and e['spell_id']==6673]
            checks={'ordinary_tab_click':s,'selected_visible_log':result['selected']==2 and result['visible'],
                'new_owned_public_event':bool(events),'new_stock_message':result['message_count']>baseline['message_count'],
                'stock_battle_shout_text':any(r['contains_battle_shout'] for r in result['recent_messages']),
                'native_cast_pass':any(c['id']=='spellbook.cast_spell' and c['status']=='spellbook_cast_pass' for c in t.receipt['cases']),
                'buff_restored':t.receipt.get('buffs_restored') is True,
                'clean':not a.get('lua_errors') and not a.get('blocked_actions')}
            return {'status':'native_stock_combat_log_pass' if all(checks.values()) else 'client_or_protocol_failure',
                'oracle':{'checks':checks,'events':events,'public':result,'chat':chat}}
        require(click(t,'chat.combat_log','Inspect the real native Battle Shout outcome in the stock Combat Log.',
            lambda c:c['name']=='ChatFrame2Tab' and c['text']=='Combat Log',logged),'native_stock_combat_log_pass')
        state,frame=t.observe('native_combat_log_rendered')
        t.receipt['combat_log_rendered']={'state':state,'frame':frame};t.persist()
    finally:
        t.clean_panels();current=chat_detail(t,'combat_log_cleanup_chat')
        if current['selected']!=original['selected']:
            require(click(t,'fixture.restore_general_after_native_log','Restore the original General tab.',lambda c:
                c['name']=='ChatFrame1Tab' and c['text']=='General',lambda b,a,s:{'status':'chat_selection_restored'
                if s and chat_detail(t,'combat_log_restored_selection')['selected']==1 else
                'client_or_protocol_failure'}),'chat_selection_restored')
        after=chat_detail(t,'combat_log_restored_chat')
        checks={'original_chat_settings':signature(original)==signature(after),'settings_closed':not after['settings_visible']}
        t.receipt['combat_log_chat_restoration']={'checks':checks,'public':after};t.persist()
        if not all(checks.values()):raise RuntimeError('original chat settings differ after real logging')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    mode=p.add_mutually_exclusive_group();mode.add_argument('--settings-recon',action='store_true')
    mode.add_argument('--message-types-recon',action='store_true');a=p.parse_args()
    t=Trial(a.output,controller='code')
    try:native_suite(t,operations=(lambda t:settings_recon(t,a.message_types_recon)) if
        a.settings_recon or a.message_types_recon else run,preserve_settings=False);t.receipt['completed']=True
    except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
