"""Verify the exact rejected AddOns-panel fixture after its observation repair."""
import argparse,json,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_trial import Trial
from .interaction_keybindings_native import suite
from .interaction_stance_bar import restored_native_state


def verify(t,source):
    source=source.resolve()
    if source.name!='episode.json' or not source.is_relative_to(lab.ROOT/'evidence'):
        raise ValueError('require a private closed AddOns failure')
    old=json.loads(source.read_text())
    if (old['actor']!=t.fixture or old['runtime']!=t.receipt['runtime'] or old['completed'] or
        not old.get('finished_at') or old['failure']!=
        'RuntimeError: operation did not advance: settings.inspect_menu client_or_protocol_failure' or
        not any(c['id']=='menu.addons' and c['status']=='client_or_protocol_failure' for c in old['cases'])):
        raise RuntimeError('exact AddOns failure identity differs')
    t.receipt['source']={'file':str(source),'sha256':lab.sha256(source)};t.persist()
    def unchanged(trial):
        before=old['native_baseline'];now=trial.receipt['native_baseline']
        checks={k:now[k]==before[k] for k in ['resources','spells','actions','pose','afk','position']}
        checks['stats']=restored_native_state(before['stats'],now['stats'])
        checks['settings']=trial.receipt['settings_details']['original_settings']['state']['settings_probe']==\
            old['settings_details']['original_settings']['state']['settings_probe']
        trial.receipt['source_fixture_checks']=checks;trial.persist()
        if not all(checks.values()):raise RuntimeError('original rejected AddOns fixture differs')
    suite(t,unchanged)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();t=Trial(a.output,controller='code')
    try:verify(t,a.source);t.receipt['completed']=True
    except Exception as error:t.receipt['failure']=f'{type(error).__name__}: {error}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
