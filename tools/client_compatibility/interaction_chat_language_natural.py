"""Exercise the stock language controls on an owned native dwarf fixture."""
import argparse,json,time
from pathlib import Path
from .interaction_trial import Trial
from .interaction_chat_language import choose,send
from .interaction_chat_window import detail
from .interaction_chat_settings import signature
from .interaction_keybindings_native import suite as native_suite
from .interaction_spellbook_navigation import known
from .interaction_spellbook_professions import skills
from . import actors


def play(t):
    if t.fixture['actor']!='scout' or t.fixture['race']!=3 or t.fixture['class']!=1 or t.fixture['level']!=1:
        raise RuntimeError('requires the owned level1 dwarf warrior fixture')
    before=detail(t,'natural_language_original');rows=before['languages']
    if not rows.get('available') or {r['id'] for r in rows['rows']}!={6,7} or rows.get('selected_id') is not None:
        raise RuntimeError('native racial language choices are not the exact expected baseline')
    native={'spells':known(t.fixture['guid']),'skills':skills(t.fixture['guid'])}
    if [111,300,300] not in native['skills']:
        raise RuntimeError('native racial fixed skill range differs')
    session=actors.session_entry(t.fixture)['session']
    t.receipt.update(language_baseline=before,natural_language_baseline=native,session=session);t.persist()
    try:
        choose(t,6,'chat.language_switch');send(t,session,6,'chat.language_switch')
        choose(t,7,'fixture.language_restore_common');send(t,session,7,'fixture.language_restore_common')
    finally:
        t.clean_panels();current=detail(t,'natural_language_cleanup_guard')
        if current['languages'].get('selected_id')==6:choose(t,7,'fixture.language_recover_common')
        elif current['languages'].get('selected_id') not in [None,7]:
            raise RuntimeError('refuses an unrelated language choice during cleanup')
        t.execute({'kind':'chat','value':'/reload'});after=detail(t,'natural_language_restored')
        checks={'languages':after['languages']==before['languages'],'chat_settings':signature(after)==signature(before),
            'channels':after['channels']==before['channels'],'spells':known(t.fixture['guid'])==native['spells'],
            'skills':skills(t.fixture['guid'])==native['skills']}
        t.receipt['language_restoration']={'checks':checks,'public':after};t.persist()
        if not all(checks.values()):raise RuntimeError('natural language fixture restoration differs')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    t=Trial(a.output,controller='code')
    try:native_suite(t,operations=play,preserve_settings=False);t.receipt['completed']=True
    except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
    finally:
        t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ['completed','failure']}),flush=True)
