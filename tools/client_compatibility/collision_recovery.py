"""Bound local recovery using observed player displacement, never find targets."""
import math


class Recovery:
    def __init__(self):
        self.checked=None;self.blocked=0;self.attempts=0

    def update(self,history,tcp):
        previous=next((s for s in reversed(history) if s['action'].startswith('forward_')),None)
        if not previous or previous['index']==self.checked or not tcp.get('player'):return
        self.checked=previous['index']
        before=previous['tcp'].get('player')
        if not before:return
        distance=math.dist(before['position'][:2],tcp['player']['position'][:2])
        expected=(previous['input']['hold_seconds'] or .5)*7
        if distance<max(.75,expected*.2):self.blocked+=1
        else:self.blocked=0;self.attempts=0

    def for_action(self,action):
        if not action.startswith('forward_') or self.blocked<2:return None
        if self.attempts>=3:raise RuntimeError('three local collision recoveries failed to restore movement')
        self.attempts+=1
        return {'attempt':self.attempts,'blocked_forward_attempts':self.blocked,
                'source':'owned_player_displacement','decision_origin':'physical_movement_guard'}
