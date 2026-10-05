"""Compare added public route facts against an unchanged retained Laya head.

This makes no game inputs and does not update any model weights. The old
direction/color input slot is a compatibility encoding of the selected guide,
with its true source explicitly included in the request and evidence.
"""
import argparse
import copy
import json
from pathlib import Path
import urllib.request
from . import runtime
from tools.client_compatibility import archaeology_policy as policy


def run(output):
    with urllib.request.urlopen('http://127.0.0.1:8004/health',timeout=5) as r:
        health=json.load(r)
    model=health['heads']['archaeology']
    rows=[]
    for source in ('telescope line','GatherMate marker'):
        for action in policy.ACTIONS:
            s={'task':'recover an archaeology find','available':True,'casting':False,
               'artifact_visible':False,'instrument_current':True,
               'telescope':{'color':'red','heading_relative_to_player':'aligned'}}
            if action=='survey': s.update(instrument_current=False,telescope=None)
            elif action=='observe': s['casting']=True
            elif action=='loot': s['artifact_visible']=True
            elif action.startswith('turn_'): s['telescope']['heading_relative_to_player']=action[5:]
            elif action=='forward_short': s['telescope']['color']='green'
            distance=0 if action=='survey' else 3 if action=='forward_short' else 131
            for variant in ('unchanged','distance_only','source_only','route_facts'):
                state=copy.deepcopy(s)
                if variant=='distance_only' and state['telescope']:
                    state['telescope']['distance_yards']=distance
                if variant=='source_only': state['source']=source
                if variant=='route_facts':
                    state['addon']={'source':source,'distance_yards':distance,
                        'mounted':False,'flying':False,'arrived':action=='survey',
                        'last_survey':'telescope' if source=='telescope line' else 'not at marker yet',
                        'last_pickup':'confirmed',
                        'direction_input':'telescope field encodes selected addon guide'}
                req={'model':model['model'],'policy':'archaeology','state':state}
                request=urllib.request.Request('http://127.0.0.1:8004/v1/systemone',
                    data=json.dumps(req).encode(),headers={'Content-Type':'application/json'})
                with urllib.request.urlopen(request,timeout=10) as r: result=json.load(r)
                choice=result['answers']['action']['choice']
                complete=not any(v['truncated_fields'] for v in result['token_budget'].values())
                rows.append({'source':source,'variant':variant,'expected':action,'choice':choice,
                    'correct':choice==action and complete and result['revision']==model['revision'],
                    'request':req,'response':result})
    summary={variant:{'correct':sum(r['correct'] for r in rows if r['variant']==variant),
                      'total':sum(r['variant']==variant for r in rows)}
             for variant in ('unchanged','distance_only','source_only','route_facts')}
    runtime.write(output,{'schema':'whitemane_unchanged_head_context_comparison_v1',
        'model':model,'question_changed':False,'weights_changed':False,
        'game_inputs_sent':False,'summary':summary,'cases':rows})
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    print(json.dumps(run(parser.parse_args().output)))
