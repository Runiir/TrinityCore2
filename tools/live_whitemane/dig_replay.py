"""Replay closed digging observations through Laya without sending game input."""
import argparse
import json
import random
import statistics
from pathlib import Path
from . import dig_context,dig_decisions,runtime


def run(session_path, output, seed=442):
    session_path=session_path.resolve();output=output.resolve()
    if not session_path.is_relative_to(runtime.ROOT/'evidence') or not output.is_relative_to(runtime.ROOT/'evidence'):
        raise ValueError('replay must use owned public evidence')
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    session=json.loads(session_path.read_text());steps=session['steps']
    random.seed(seed)
    cases=[]
    for index in range(max(3,len(steps)-12),len(steps)):
        old=steps[index]
        state=dig_context.model_state(old['before'],old.get('guide'),old['state']['artifact_visible'],
            old['before'].get('pending_find'),steps[:index])
        for draw in range(4):
            action,model,request,response=dig_decisions.choose(state)
            record={'saved_step':old['index'],'draw':draw,'baseline_action':old['action'],
                'replay_action':action,'model':model,'request':request,'response':response,
                'gameplay_inputs':0,'pickup_verified':False}
            runtime.write(output/f'case_{index:03d}_{draw}.json',record)
            cases.append(record)
    if not cases:raise ValueError('replay needs at least four completed saved observations')
    progress=lambda action:action=='loot' or action.startswith('forward_')
    metrics={'cases':len(cases),'baseline_approach_or_interact_choices':sum(progress(c['baseline_action']) for c in cases),
        'context_argmax_approach_or_interact_choices':sum(progress(c['response']['answers']['action']['choice']) for c in cases),
        'replay_approach_or_interact_choices':sum(progress(c['replay_action']) for c in cases),
        'sampled_choices':sum('policy_selection' in c['response'] for c in cases),
        'input_tokens_max':max(c['response']['token_budget']['action']['input_tokens'] for c in cases),
        'inference_median_ms':statistics.median(c['response']['elapsed_sec'] for c in cases)*1000,
        'gameplay_inputs':0,'confirmed_pickups':0}
    runtime.write(output/'summary.json',{'seed':seed,'session':str(session_path),'metrics':metrics,
        'acceptance':'offline selection check only; no movement or pickup qualification'})
    return metrics


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--seed',type=int,default=442)
    args=parser.parse_args()
    print(json.dumps(run(args.session,args.output,args.seed)))
