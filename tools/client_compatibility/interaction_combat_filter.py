"""Use and remove one exact disposable stock combat filter before qualification."""
import argparse,json,time
from pathlib import Path
from .interaction_trial import Trial
from .interaction_keybindings_native import suite as native_suite
from .interaction_combat_log import probe,run as real_log
from .interaction_chat_window import menu,option,detail
from .interaction_chat_settings import signature
from .interaction_control_target import click,edit
from .interaction_macros import require

NAME='TC442Log'


def opened(t):
    menu(t,2,'fixture.owned_combat_filter_menu')
    require(option(t,'fixture.open_owned_combat_filter','Settings',lambda b,a,s:{'status':'combat_settings_open'
        if s and 'ChatConfigFrame' in a['panels'] else 'client_or_protocol_failure'}),'combat_settings_open')


def log_tab(t,label,index=2):
    require(click(t,label,'Select the observed stock chat tab.',lambda c:c['name']=='ChatFrame'+str(index)+'Tab',
        lambda b,a,s:{'status':'chat_selection_pass' if s and detail(t,label+'_result')['selected']==index
            else 'client_or_protocol_failure'}),'chat_selection_pass')


def closed(t,label):
    require(click(t,label,'Close the observed stock combat settings with Okay.',lambda c:
        c['name']=='ChatConfigFrameOkayButton' and c['text']=='Okay',lambda b,a,s:{'status':'combat_settings_closed'
        if s and 'ChatConfigFrame' not in a['panels'] else 'client_or_protocol_failure'}),'combat_settings_closed')


def owned(probe):
    return [f for f in probe['filters'] if f['name']==NAME]


def cycle(t,with_cast):
    before=probe(t,'owned_combat_filter_original');chat=detail(t,'owned_combat_filter_original_chat')
    if before['current_filter']!=1 or chat['selected']!=1 or owned(before) or not before['saved_settings']['available']:
        raise RuntimeError('requires original filter1/General and absent disposable filter name')
    original_count=len(before['filters']);t.receipt['owned_combat_filter_baseline']=before;t.persist()
    try:
        opened(t);current=probe(t,'owned_combat_filter_copy_guard')
        if current['settings_filter']!=1 or current['filter_name']!=before['filters'][0]['name']:
            raise RuntimeError('stock settings are not selecting the original filter to copy')
        require(click(t,'fixture.copy_combat_filter','Copy the observed original filter into an owned disposable filter.',
            lambda c:c['name']=='ChatConfigCombatSettingsFiltersCopyFilterButton' and c['text']=='Copy Filter',lambda b,a,s:
            {'status':'owned_filter_name_dialog' if s and 'StaticPopup1' in a['panels'] else
                'client_or_protocol_failure'}),'owned_filter_name_dialog')
        require(edit(t,'fixture.name_combat_filter','Enter the exact disposable combat-filter name.',lambda c:
            c['name']=='StaticPopup1EditBox',NAME),'ui_edit_pass')
        def copied(b,a,s):
            result=probe(t,'owned_combat_filter_created');matches=owned(result)
            checks={'ordinary_accept':s,'unique_owned_copy':len(matches)==1 and matches[0]['id']==original_count+1,
                'one_appended_filter':len(result['filters'])==original_count+1,'owned_settings_selected':result['filter_name']==NAME}
            return {'status':'owned_filter_created' if all(checks.values()) else 'client_or_protocol_failure',
                'oracle':{'checks':checks,'public':result}}
        require(click(t,'fixture.accept_combat_filter','Accept the exact disposable filter name.',lambda c:
            c['name']=='StaticPopup1Button1',copied),'owned_filter_created')
        require(click(t,'fixture.owned_filter_message_types','Select the observed Message Types tab.',lambda c:
            c['name']=='CombatConfigTab2' and c['text']=='Message Types',lambda b,a,s:{'status':'message_types_selected'
            if s and 'ChatConfigFrame' in a['panels'] else 'client_or_protocol_failure'}),'message_types_selected')
        def enabled(b,a,s):
            result=probe(t,'owned_combat_cast_filter_enabled')
            checks={'ordinary_checkbox':s,'owned_only':result['filter_name']==NAME and result['settings_filter']==original_count+1,
                'cast_success_enabled':bool(result['cast_success_enabled'] and result['cast_success_enabled'][0] is True)}
            return {'status':'owned_cast_filter_enabled' if all(checks.values()) else 'client_or_protocol_failure',
                'oracle':{'checks':checks,'public':result}}
        require(click(t,'fixture.enable_owned_spell_casting','Enable Spell Casting only on the disposable copy.',lambda c:
            c['name']=='CombatConfigMessageTypesRightCheckbox2' and c['text']=='Spell Casting' and
            c.get('checked') is False,enabled),'owned_cast_filter_enabled')
        closed(t,'fixture.save_owned_combat_filter');log_tab(t,'fixture.show_owned_filter_log')
        def activated(b,a,s):
            result=probe(t,'owned_combat_filter_activated')
            checks={'ordinary_quick_button':s,'owned_active':result['current_filter']==original_count+1 and result['filter_name']==NAME,
                'cast_success_active':bool(result['cast_success_enabled'] and result['cast_success_enabled'][0] is True)}
            return {'status':'owned_filter_active' if all(checks.values()) else 'client_or_protocol_failure',
                'oracle':{'checks':checks,'public':result}}
        require(click(t,'fixture.activate_owned_combat_filter','Activate the observed disposable quick filter.',lambda c:
            c['name'].startswith('CombatLogQuickButtonFrame') and c['text']==NAME,activated),'owned_filter_active')
        log_tab(t,'fixture.general_before_owned_log',1)
        if with_cast:real_log(t)
    finally:
        t.clean_panels();current=probe(t,'owned_combat_filter_cleanup_guard');matches=owned(current)
        if len(matches)>1:raise RuntimeError('cleanup refuses ambiguous owned filter names')
        if matches:
            index=matches[0]['id']
            if index!=original_count+1 or current['current_filter'] not in (1,index):
                raise RuntimeError('cleanup refuses a different filter index or unrelated active filter')
            opened(t)
            require(click(t,'fixture.select_owned_filter_for_delete','Select only the exact disposable filter for deletion.',
                lambda c:c['name']=='ChatConfigCombatSettingsFiltersButton'+str(index) and c['text']==NAME,
                lambda b,a,s:{'status':'owned_filter_delete_selected' if s and
                    probe(t,'owned_combat_filter_delete_guard')['filter_name']==NAME else
                    'client_or_protocol_failure'}),'owned_filter_delete_selected')
            def deleted(b,a,s):
                result=probe(t,'owned_combat_filter_deleted')
                status='owned_filter_deleted' if s and not owned(result) else (
                    'owned_delete_confirmation' if s and 'StaticPopup1' in a['panels'] else 'client_or_protocol_failure')
                return {'status':status,'oracle':{'public':result}}
            result=click(t,'fixture.delete_owned_combat_filter','Delete only the exact selected disposable filter.',
                lambda c:c['name']=='ChatConfigCombatSettingsFiltersDeleteButton' and c['text']=='Delete',deleted)
            if result['status']=='owned_delete_confirmation':
                result=click(t,'fixture.confirm_owned_filter_delete','Confirm the observed owned-filter deletion.',
                    lambda c:c['name']=='StaticPopup1Button1',deleted)
            require(result,'owned_filter_deleted');closed(t,'fixture.close_deleted_combat_filter')
        t.clean_panels();current=detail(t,'owned_combat_filter_cleanup_chat')
        if current['selected']!=1:log_tab(t,'fixture.restore_general_after_owned_filter',1)
        after=probe(t,'owned_combat_filter_restored');after_chat=detail(t,'owned_combat_filter_restored_chat')
        checks={'saved_settings_fingerprint':after['saved_settings']==before['saved_settings'],
            'original_filter_metadata':after['filters']==before['filters'],'original_active_filter':after['current_filter']==1,
            'no_owned_filter':not owned(after),'original_chat_settings':signature(chat)==signature(after_chat)}
        t.receipt['owned_combat_filter_restoration']={'checks':checks,'public':after};t.persist()
        if not all(checks.values()):raise RuntimeError('original saved combat preferences differ after owned-filter cleanup')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--with-cast',action='store_true');a=p.parse_args();t=Trial(a.output,controller='code')
    try:native_suite(t,operations=lambda t:cycle(t,a.with_cast),preserve_settings=False);t.receipt['completed']=True
    except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
