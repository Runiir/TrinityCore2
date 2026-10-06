"""Bounded priority queue of activities already selected by Laya."""
import time
from . import pending_find


def priority(action,row):
    if action=='combat':return 100
    if action=='dig' and pending_find.facts(row,row.get('pending_find'))['uncollected']:return 80
    if action=='land':return 60
    if action.startswith('solve'):return 40
    return 20 if action in ('dig','flight','portal','taxi') else 10


class IntentQueue:
    def __init__(self,session):
        self.session=session
        self.jobs=session.setdefault('accepted_activity_queue',[])

    def offer(self,action,target,decision,row):
        if action=='wait':return
        key=(action,row['archaeology'].get('site_id') if action=='dig' else None)
        self.jobs[:]=[job for job in self.jobs if (job['action'],job.get('site_id'))!=key]
        self.jobs.append({'action':action,'target':target,'site_id':key[1],
            'runtime':row['runtime'],'priority':priority(action,row),
            'selected_at':time.time(),'selection':decision,'selected_by':'Laya'})
        self.jobs.sort(key=lambda job:(-job['priority'],job['selected_at']))
        del self.jobs[4:]

    def retained(self,row,options):
        minimum=100 if row['movement']['in_combat'] else 40 if any(
            action.startswith('solve_') for action in options) else 0
        for job in sorted(self.jobs,key=lambda item:-priority(item['action'],row)):
            action=job['action']
            if (action!='dig' or action not in options or job['runtime']!=row['runtime']
                    or priority(action,row)<minimum):continue
            if (job['site_id']!=row['archaeology'].get('site_id')
                    and not row.get('pending_find')):continue
            return action,job['target'],{**job['selection'],
                'model_decision_reused':True,'selection_method':'retained_accepted_Laya_activity',
                'accepted_at':job['selected_at'],'current_priority':priority(action,row)}
        return None

    def finish(self,action,*,retain=False):
        if not retain:self.jobs[:]=[job for job in self.jobs if job['action']!=action]
