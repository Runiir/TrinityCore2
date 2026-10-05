"""Use observed owned-client turns to time one physical turn toward a waypoint."""
import math
import statistics


def turn_duration(error, history):
    samples=[]
    for step in history[-40:]:
        if not step.get('completed') or step.get('action') not in ('turn_left','turn_right'):continue
        before=step['before']['movement']['facing_radians']
        after=step['after']['movement']['facing_radians']
        delta=(after-before+math.pi)%math.tau-math.pi
        for receipt in step.get('inputs',[]):
            arguments=receipt.get('arguments',{})
            if arguments.get('key') not in ('Left','Right'):continue
            hold=arguments.get('hold',0)
            if hold and abs(delta)>.1 and (delta>0)==(step['action']=='turn_left'):
                rate=abs(delta)/hold
                if 1<=rate<=6:samples.append({'step':step['index'],'radians_per_second':rate})
    rate=statistics.median(s['radians_per_second'] for s in samples) if samples else math.pi
    duration=max(.05,min(1.25,abs(error)/rate))
    return duration,{'radians_per_second':rate,'samples':samples,'error_radians':error,
                     'basis':'median of owned live turns' if samples else 'initial 180 degree per second estimate'}
