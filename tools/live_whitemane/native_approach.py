"""Observed native-interaction range refusals, without movement or action selection."""
import json
import math
import time
from . import runtime,action_queue,pending_find


def recent_refusal(row,name):
    path=runtime.ROOT/'run/native_approach_refusal.json'
    if not path.exists():return False
    refusal=json.loads(path.read_text());old=refusal.get('world');world=row['archaeology'].get('world')
    return (refusal.get('runtime')==row.get('runtime') and refusal.get('name')==name
        and refusal.get('looted_finds')==row['archaeology'].get('looted_finds')
        and 0<=time.time()-refusal['at']<30 and old and world and old['instance']==world['instance']
        and math.hypot(world['north']-old['north'],world['west']-old['west'])<1)


class Feedback:
    """Two fresh stationary movement samples distinguish refusal from approach."""
    def __init__(self,before,interaction=None):
        self.before=before;self.interaction=interaction or {}
        self.name=self.interaction.get('name') or before.get('farm_ui',{}).get('tooltip')
        self.sent_uptime=self.interaction.get('client_uptime_at_click',before.get('farm_ui',{}).get('uptime',0))
        self.world=before['archaeology'].get('world');self.sequence=before['movement'].get('sequence')
        self.stationary_samples=0

    def refused(self,row):
        error=(row.get('farm_ui') or {}).get('error') or {}
        if (not pending_find.range_error(error) or error.get('at',0)<self.sent_uptime
                or action_queue.busy(row,uses_gcd=False)):
            self.stationary_samples=0;return False
        sequence=row['movement'].get('sequence')
        if sequence is None or sequence==self.sequence:return False
        self.sequence=sequence;world=row['archaeology'].get('world');old=self.world;self.world=world
        stationary=(row['movement'].get('speed',0)==0 and old and world and old['instance']==world['instance']
            and math.hypot(world['north']-old['north'],world['west']-old['west'])<=.1)
        self.stationary_samples=self.stationary_samples+1 if stationary else 0
        if self.stationary_samples<2:return False
        runtime.write(runtime.ROOT/'run/native_approach_refusal.json',{
            'runtime':row.get('runtime'),'name':self.name,'world':world,'at':time.time(),
            'looted_finds':row['archaeology'].get('looted_finds'),
            'observed_error':error,'fresh_stationary_samples':self.stationary_samples,
            'fact':'native interaction reported out of range without approaching'})
        return True
