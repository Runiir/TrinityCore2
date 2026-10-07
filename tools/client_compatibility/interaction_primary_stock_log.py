"""Select the observed stock Combat Log tab and restore General afterwards."""
import argparse,json,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_social import actor
from .interaction_trial import Trial
from .interaction_primary_melee_diagnostic import source
from .interaction_control_target import click
from .interaction_combat_log import probe
from .interaction_macros import require
from .interaction_owned_class_fixture import SCRIPT_BOUNDARY


def run(t,path,restore=False):
    d=json.loads(path.read_text())
    if restore:
        if (path.is_symlink() or not path.resolve().is_relative_to(lab.ROOT/'evidence') or
            not d.get('finished_at') or d.get('completed') is not True or d.get('failure') is not None or
            d.get('actor')!=t.fixture or d.get('runtime')!=t.receipt['runtime'] or
            d.get('phase')!='primary_stock_log_selected'):
            raise RuntimeError('requires the closed owned stock-tab selection')
        baseline=d['baseline'];t.receipt['source']={'path':str(path.resolve()),'sha256':lab.sha256(path)}
    else:
        d=source(t,path,'owned_primary_combat_preparation')
        if len(d['reentry_checks'])!=15 or not all(d['reentry_checks'].values()):raise RuntimeError('entry guards incomplete')
        baseline=probe(t,'stock_log_original')
        if baseline['selected']!=1:raise RuntimeError('requires original General tab')
    t.receipt.update(baseline=baseline,qualification_added=False);t.persist()
    number=1 if restore else 2;caption='General' if restore else 'Combat Log'
    def selected(b,a,ordinary):
        result=probe(t,'stock_log_selected')
        checks={'ordinary_click':ordinary,'selected':result['selected']==number,
            'visible':bool(result['visible']) if not restore else True,
            'saved_filters':result['saved_settings']==baseline['saved_settings'],
            'ui_clean':not a.get('lua_errors') and not a.get('blocked_actions')}
        t.receipt['checks']=checks;t.receipt['public']=result;t.persist()
        return {'status':'stock_tab_selected' if all(checks.values()) else 'client_or_protocol_failure'}
    require(click(t,'stock_log.tab','Select the observed '+caption+' stock chat tab.',
        lambda c:c['name']=='ChatFrame'+str(number)+'Tab' and c['text']==caption,selected),'stock_tab_selected')
    state,frame=t.observe('stock_log_rendered')
    t.receipt.update(frame=frame,completed=True,phase='primary_stock_log_restored' if restore else 'primary_stock_log_selected',
        qualified_scope='Stock tab selection only; no damage-log or gameplay qualification.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['open','restore'])
    p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    with actor('primary'):
        t=Trial(a.output,controller='code',chat_key_hold=1.2,chat_open_retry=True)
        t.receipt.update(custom_script_permission='blocked_by_user',softTargetInteract=SCRIPT_BOUNDARY)
        try:run(t,a.source,a.action=='restore')
        except Exception as e:t.receipt.update(completed=False,failure=f'{type(e).__name__}: {e}')
        finally:t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({k:t.receipt.get(k) for k in ('completed','failure','checks')}),flush=True)
