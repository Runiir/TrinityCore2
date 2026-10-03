"""Restore the exact scout visibility changed by a closed failed protocol trial."""
import json
from . import actors,lab_runtime as lab
from .interaction_character_appearance import flags,toggle
from .interaction_settings_search import resources,open_search
from .interaction_operations import controls,point,click_case
from .interaction_macros import edit_case,require
from .observation.inventory import Inventory
from .interaction_equipment_set_roundtrip import stable
from .interaction_tooltips import baseline


def owned_json(path):
    path=path.resolve()
    if not path.is_relative_to(lab.ROOT/'evidence'):raise ValueError('require owned evidence')
    return json.loads(path.read_text()),{'file':str(path),'sha256':lab.sha256(path)}


def comparable_flags(value):
    # Ordinary client input clears idle AFK. It is not a saved appearance bit.
    return {**value,'native_player_flags':value['native_player_flags']&~2}


def snapshot(t,oracle):
    return stable(baseline()) if t.fixture['guid']==1 else resources(oracle)


def close_source(t,source):
    old,ref=owned_json(source);session=actors.session_entry(t.fixture)['session']
    oracle=Inventory(lab.ROOT,session,t.fixture['guid']).poll()
    changed=[c['oracle']['native'] for c in old['cases'] if c.get('oracle',{}).get('native')]
    before=flags(t,oracle)
    if (old.get('completed') or not old.get('finished_at') or old['actor']!=t.fixture or
        t.fixture['guid']!=2 or old['runtime']!=t.receipt['runtime'] or not changed or
        comparable_flags(before)!=comparable_flags(changed[-1]) or
        resources(oracle)!=old['baseline']):raise RuntimeError('require the exact failed scout and unchanged mutation')
    t.receipt.update(source=ref,baseline=old['baseline'],native_before=before,
        qualified_scope='Source-bound settings search and panel closure; native hidden state remains pending');t.persist()
    try:
        field=old['search_field'];predicate=lambda c:c['kind']=='EditBox' and point(c)==point(field)
        require(edit_case(t,'appearance.close_restore_search','Restore the original stock search.',predicate,field['text']),'ui_edit_pass')
        require(click_case(t,'appearance.close_pending_settings','Close the visible stock settings window.',lambda c:c['text']=='Close',
            lambda b,a,s:{'status':'panel_closed_pass' if s and 'SettingsPanel' not in a['panels'] else 'client_or_protocol_failure'},
            await_state=lambda a:'SettingsPanel' not in a['panels']),'panel_closed_pass')
        t.clean_panels()
    finally:
        t.receipt['native_after']=resources(oracle);t.receipt['native_visibility_after']=flags(t,oracle)
        t.receipt['native_resources_preserved']=t.receipt['native_after']==old['baseline'];t.persist()
    if not t.receipt['native_resources_preserved'] or comparable_flags(t.receipt['native_visibility_after'])!=comparable_flags(before):
        raise RuntimeError('panel closure changed the attributable native fixture')


def recover(t,source,deployment):
    old,source_ref=owned_json(source);deploy,deploy_ref=owned_json(deployment/'deployment.json')
    name=t.fixture['actor']
    before,_=owned_json(deployment/(name+'_before/episode.json'))
    after,_=owned_json(deployment/(name+'_after/episode.json'))
    original=old['appearance_baseline'];session=actors.session_entry(t.fixture)['session']
    oracle=Inventory(lab.ROOT,session,t.fixture['guid']).poll()
    changed=[c['oracle']['native'] for c in old['cases'] if c.get('oracle',{}).get('native') and
        c['id'] in ['character.display_helm','appearance.cleanup.helm','appearance.recovery_restore_helm']]
    current=flags(t,oracle)
    if (old.get('completed') or not old.get('finished_at') or old['actor']!=t.fixture or t.fixture['guid'] not in [1,2] or
        not old.get('native_resources_preserved') or not deploy.get('completed') or not after.get('completed') or
        deploy['native']!=old['runtime']['worldserver'] or deploy['native']!=t.receipt['runtime']['worldserver'] or
        deploy['before']!=old['runtime']['modern_world'] or deploy['after']!=t.receipt['runtime']['modern_world'] or
        before['runtime']['client']!=old['runtime']['client'] or after['runtime']['client']!=t.receipt['runtime']['client'] or
        not changed or comparable_flags(current)!=comparable_flags(changed[-1]) or snapshot(t,oracle)!=old['baseline'] or
        any((comparable_flags(current)[k]^comparable_flags(original['native'])[k])!=0x400 for k in current) or
        (t.fixture['guid']==2 and (oracle.equipment(1)['guid'] or oracle.equipment(15)['guid']))):
        raise RuntimeError('recovery requires the exact failed owned helm mutation and completed owned deployment')
    t.receipt.update(source=source_ref,deployment_source=deploy_ref,baseline=old['baseline'],
        appearance_baseline=original,native_before=current,native_session=session,
        qualified_scope='Source-bound restoration of the failed owned fixture only');t.persist()
    try:
        t.clean_panels();field=open_search(t);predicate=lambda c:c['kind']=='EditBox' and point(c)==point(field)
        require(edit_case(t,'appearance.recovery_find','Find the original stock helm setting.',predicate,'helm'),'ui_edit_pass')
        rows=[c for c in controls(t) if c['kind']=='CheckButton' and c.get('context')=='Show Helm']
        state,frame=t.observe('native_hidden_before_restore')
        if len(rows)!=1 or rows[0].get('checked') is not False or state['appearance']['helm'] is not False:
            raise RuntimeError('the repaired client does not acknowledge the attributable native hidden helm')
        t.receipt['native_hidden_before_restore']={'state':state,'controls':rows,'frame':frame};t.persist()
        require(toggle(t,oracle,'helm',original['state']['helm'],'appearance.recovery_restore_helm'),'character_appearance_pass')
        search=old['search_field']['text']
        require(edit_case(t,'appearance.recovery_search','Restore the source settings search.',predicate,search),'ui_edit_pass')
        require(click_case(t,'appearance.recovery_close','Close stock settings.',lambda c:c['text']=='Close',
            lambda b,a,s:{'status':'panel_closed_pass' if s and 'SettingsPanel' not in a['panels'] else 'client_or_protocol_failure'},
            await_state=lambda a:'SettingsPanel' not in a['panels']),'panel_closed_pass')
        t.clean_panels();t.execute({'kind':'chat','value':'/reload'})
        state,frame=t.observe('original_visibility_restored')
        t.receipt['appearance_restored']={'state':state['appearance'],'native':flags(t,oracle),'frame':frame};t.persist()
        if state['appearance']!=original['state'] or t.receipt['appearance_restored']['native']!=original['native']:
            raise RuntimeError('source visibility did not restore and survive ordinary reload')
    finally:
        t.receipt['native_after']=snapshot(t,oracle);t.receipt['native_resources_preserved']=t.receipt['native_after']==old['baseline']
        t.receipt['native_visibility_after']=flags(t,oracle);t.persist()
    if not t.receipt['native_resources_preserved']:raise RuntimeError('recovery changed native equipment or money')
