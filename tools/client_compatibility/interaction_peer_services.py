"""Probe inspect and trade through ordinary input on two nearby owned characters."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_social import actor
from .nearby_fixture import NearbyFixture


def suite(out):
    out.mkdir(parents=True,exist_ok=False,mode=0o700)
    cohort={'started_at':time.time(),'completed':False,'failure':None};trials={};fixture=None;failed=False
    try:
        for name in ['primary','scout']:
            with actor(name):
                t=trials[name]=Trial(out/name);actors.session_entry(t.fixture);t.clean_panels()
        fixture=NearbyFixture(out,trials['primary'].fixture,trials['scout'].fixture,open_ground=True);fixture.prepare()
        for name,t in trials.items():
            other,other_guid=('Harnesstwo',2) if name=='primary' else ('Harnessone',1)
            with actor(name):
                t.execute({'kind':'chat','value':'/targetexact '+other})
                def inspected(b,a,s):
                    inspect=a.get('inspect',{});passed=inspect.get('visible') and inspect.get('guid')==f'Player-1-{other_guid:08X}'
                    return {'status':'inspect_panel_pass' if s=='inspect' and passed else
                        ('controller_failure' if s!='inspect' else 'client_or_protocol_failure'),
                        'oracle':{'inspect':inspect,'target':a['target'],'qualified_scope':'inspect opening only; equipment/talents checked separately'}}
                row=t.step('player.inspect_nearby','Inspect the nearby owned player '+other+'.',{
                    'inspect':{'kind':'chat','value':'/inspect','description':'Type /inspect to inspect the targeted player.'},
                    'character':{'kind':'key','value':'c','description':'Open your own character equipment window.'},
                    'map':{'kind':'key','value':'m','description':'Open the map.'}},inspected)
                failed|=row['status']!='inspect_panel_pass';t.clean_panels()
        with actor('primary'):
            t=trials['primary'];t.execute({'kind':'chat','value':'/targetexact Harnesstwo'})
            row=t.step('trade.initiate','Start a trade with the nearby owned player Harnesstwo.',{
                'trade':{'kind':'chat','value':'/trade','description':'Type /trade to start a trade with the targeted player.'},
                'inspect':{'kind':'chat','value':'/inspect','description':'Inspect the targeted player.'},
                'map':{'kind':'key','value':'m','description':'Open the map.'}},
                lambda b,a,s:{'status':'trade_panel_pass' if s=='trade' and a.get('trade',{}).get('visible') else
                    ('controller_failure' if s!='trade' else 'client_or_protocol_failure'),'oracle':{'trade':a.get('trade'),'errors':a['errors']}})
            failed|=row['status']!='trade_panel_pass'
        with actor('scout'):
            s,f=trials['scout'].observe('trade_peer');trials['scout'].receipt['trade_peer']={'trade':s.get('trade'),'frame':f};trials['scout'].persist()
        if failed:raise RuntimeError('nearby inspect/trade probes have unqualified outcomes')
        cohort['completed']=True
    except Exception as e:cohort['failure']=f'{type(e).__name__}: {e}'
    finally:
        for name,t in trials.items():
            with actor(name):
                try:t.clean_panels()
                except Exception as e:cohort['completed']=False;cohort.setdefault('cleanup_failures',{})[name]=str(e)
        if fixture:
            try:fixture.restore()
            except Exception as e:cohort.update(completed=False,cleanup_failure=str(e))
        for name,t in trials.items():
            with actor(name):
                try:
                    s,_=t.observe('cleanup_target')
                    if s.get('target',{}).get('exists'):t.execute({'kind':'key','value':'Escape'})
                    s,f=t.observe('restored');t.receipt['restoration']={'frame':f,'world_position':s['world_position']}
                except Exception as e:cohort['completed']=False;cohort.setdefault('cleanup_failures',{})[name]=str(e)
            t.receipt.update(completed=cohort['completed'],failure=cohort['failure'],finished_at=time.time());t.persist()
        cohort['finished_at']=time.time();lab.private_write(out/'cohort.json',json.dumps(cohort,indent=2)+'\n');print(json.dumps(cohort),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);suite(p.parse_args().output)
