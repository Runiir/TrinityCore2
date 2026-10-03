"""Read specialization API availability before and after normal talent UI loading."""
import argparse,json,time
from pathlib import Path
from .interaction_trial import Trial
from .interaction_equipment_sets import detail,sets
from .interaction_tooltips import baseline,close_glyphs
from .interaction_macros import require


def suite(t):
    t.clean_panels();saved=baseline();catalog=sets();t.receipt['baseline']={'native':saved,'sets':catalog};t.persist()
    try:
        t.receipt['api_before']=detail(t,'equipment_apis_before');t.persist()
        require(t.step('sets.api_load_talents','Open the normal talent window to load its stock UI.',
            {'open':{'kind':'key','value':'n','description':'Press N for talents.'}},
            lambda b,a,s:{'status':'talents_open_pass' if 'PlayerTalentFrame' in a['panels'] else
                'client_or_protocol_failure'},diagnostic_action='open'),'talents_open_pass')
        t.receipt['api_after']=detail(t,'equipment_apis_after');t.persist()
        close_glyphs(t)
    finally:
        t.clean_panels();t.receipt['native_after']={'native':baseline(),'sets':sets()}
        t.receipt['native_preserved']=t.receipt['native_after']==t.receipt['baseline'];t.persist()
        if not t.receipt['native_preserved']:raise RuntimeError('read-only equipment API probe changed native state')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();t=Trial(a.output,controller='code')
    try:suite(t);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:t.receipt['finished_at']=time.time();t.persist();print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
