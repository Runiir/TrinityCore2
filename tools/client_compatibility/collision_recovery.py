"""Bound local recovery using observed player displacement, never find targets."""
import math


class Recovery:
    def __init__(self):
        self.checked=None;self.blocked=0;self.attempts=0;self.obstructions=[]

    def update(self,history,tcp):
        previous=next((s for s in reversed(history) if s['action'].startswith('forward_')),None)
        if not previous or previous['index']==self.checked or not tcp.get('player'):return
        self.checked=previous['index']
        for point in ((previous.get('input') or {}).get('ground_route') or {}).get('obstruction_origins',[]):
            if not any(math.dist(point[:2],old[:2])<2 for old in self.obstructions):
                if len(self.obstructions)>=8:raise RuntimeError('eight observed ground obstructions exhausted local recovery')
                self.obstructions.append(point)
        before=previous['tcp'].get('player')
        if not before:return
        distance=math.dist(before['position'][:2],tcp['player']['position'][:2])
        expected=(previous['input']['hold_seconds'] or .5)*7
        # A short mesh corner can intentionally move less than a yard.
        if distance<max(.07,expected*.2):self.blocked+=1
        else:self.blocked=0;self.attempts=0

    def for_action(self,action):
        if not action.startswith('forward_'):return None
        remembered={'ground_obstructions':self.obstructions.copy(),'source':'observed feet below mapped solid surface',
            'decision_origin':'physical_movement_guard'} if self.obstructions else None
        if self.blocked<2:return remembered
        if self.attempts>=3:raise RuntimeError('three local collision recoveries failed to restore movement')
        self.attempts+=1
        return {**(remembered or {}),'attempt':self.attempts,'blocked_forward_attempts':self.blocked,
                'source':'owned_player_displacement','decision_origin':'physical_movement_guard'}
