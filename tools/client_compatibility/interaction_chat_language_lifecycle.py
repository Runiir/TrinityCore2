"""Play the stock language gates, then require exact offline fixture teardown."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_keybindings_native import suite as native_suite
from .interaction_chat_language import choose,send,native_skills
from .interaction_chat_window import detail
from .interaction_chat_settings import signature
from .interaction_fixture_permissions import fixture_permission
from .interaction_spellbook_navigation import known
from .interaction_spellbook_professions import skills
from .interaction_targeting import selection,target as select_target
from .observation.inventory import Inventory


def play(t):
    if t.fixture['guid']!=1:raise RuntimeError('requires the owned primary language fixture')
    before=detail(t,'language_lifecycle_original')
    if before.get('languages')!={'available':True,'rows':[{'id':7,'name':'Common'}]}:
        raise RuntimeError('requires the exact original Common-only default selection')
    session=actors.session_entry(t.fixture)['session'];oracle=Inventory(lab.ROOT,session,1).poll()
    original={'spells':known(1),'skills':skills(1),'native_skills':native_skills(oracle),'target':selection(oracle)}
    if any(r[0]==672 for r in original['spells']) or any(r[0]==111 for r in original['skills']):
        raise RuntimeError('temporary native language already exists')
    if original['target'] not in [0,1,2]:raise RuntimeError('refuses an unrelated original target')
    t.receipt.update(language_lifecycle_schema='client442_language_lifecycle_v1',
        language_baseline=before,language_fixture_baseline=original,
        language_fixture={'spell':672,'language':6,'skill':111,'temporary':True,
            'teardown':'Normal owned logout, exact extra offline spell and skill-row removal, reviewed reentry.'},
        language_phase_completed=False);t.persist()
    with fixture_permission(t,417):
        try:
            if selection(oracle)!=1:
                select_target(t,oracle,session,'fixture.language_target_self',{'kind':'chat','value':'/target Harnessone'},1)
            t.execute({'kind':'chat','value':'.learn 672'});t.execute({'kind':'chat','value':'.save'})
            trained=detail(t,'language_lifecycle_trained')
            checks={'exact_extra_native_spell':sorted(known(1))==sorted(original['spells']+[[672,1,0]]),
                'exact_extra_native_skill':sorted(skills(1))==sorted(original['skills']+[[111,1,300]]),
                'public_languages':trained['languages'].get('available') and
                    {r['id'] for r in trained['languages']['rows']}=={6,7}}
            t.receipt['language_fixture_trained']={'checks':checks,'public':trained,'spells':known(1),
                'skills':skills(1),'native_skills':native_skills(oracle)};t.persist()
            if not all(checks.values()):raise RuntimeError('native language capability did not become available')
            choose(t,6,'chat.language_switch');send(t,session,6,'chat.language_switch')
            choose(t,7,'fixture.language_restore_common');send(t,session,7,'fixture.language_restore_common')
            t.receipt['language_phase_completed']=True;t.persist()
        except BaseException as error:
            t.receipt['language_operation_failure']=f'{type(error).__name__}: {error}';t.persist();raise
        finally:
            t.clean_panels();current=detail(t,'language_lifecycle_cleanup_guard')
            if current['languages'].get('selected_id')==6:choose(t,7,'fixture.language_recover_common')
            elif current['languages'].get('selected_id') not in [None,7]:
                raise RuntimeError('refuses an unrelated language selection during cleanup')
            t.execute({'kind':'chat','value':'/reload'})
            if selection(oracle)!=original['target']:
                command={0:'/cleartarget',1:'/target Harnessone',2:'/target Harnesstwo'}[original['target']]
                select_target(t,oracle,session,'fixture.language_restore_target',{'kind':'chat','value':command},original['target'])
            after=detail(t,'language_lifecycle_pending_cleanup')
            checks={'original_languages':after['languages']==before['languages'],
                'original_chat_settings':signature(after)==signature(before),'original_channels':after['channels']==before['channels'],
                'original_spells':known(1)==original['spells'],'original_skills':skills(1)==original['skills'],
                'original_native_skills':native_skills(oracle)==original['native_skills'],
                'original_target':selection(oracle)==original['target']}
            pending=(sorted(skills(1))==sorted(original['skills']+[[111,1,300]]) and
                sorted(known(1))==sorted(original['spells']+[[672,1,0]]))
            t.receipt.update(language_restoration={'checks':checks,'public':after},
                phase='await_offline_language_cleanup' if pending else 'language_fixture_not_added');t.persist()
            required=['original_chat_settings','original_channels','original_target']
            if not pending or not all(checks[k] for k in required):
                raise RuntimeError('non-language fixture state differs before offline cleanup')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    t=Trial(a.output,controller='code')
    try:native_suite(t,operations=play,preserve_settings=False)
    except Exception as error:
        checks=t.receipt.get('native_restoration',{}).get('checks',{})
        deferred=(str(error)=='native binding fixture restoration differs' and
            t.receipt.get('phase')=='await_offline_language_cleanup' and checks.get('spells') is False and
            all(v for k,v in checks.items() if k!='spells') and not t.receipt.get('language_operation_failure'))
        if deferred:t.receipt['native_spell_restoration_deferred']=True
        else:t.receipt['failure']=f'{type(error).__name__}: {error}'
    finally:
        t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ['phase','language_phase_completed','completed','failure']}),flush=True)
