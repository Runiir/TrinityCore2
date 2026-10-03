"""Reveal a faction with observed stock scrollbar arrows and restore the viewport."""
from contextlib import contextmanager
import re
from .interaction_operations import controls,click_case
from .interaction_macros import require


def visible(rows,public):
    names=[c['text'] for c in sorted(rows,key=lambda c:c['y'])
        if re.fullmatch(r'ReputationBar\d+',c['name']) and c['text']]
    matches=[public['rows'][start:start+len(names)] for start in range(len(public['rows'])) if names and
        [r['name'] for r in public['rows'][start:start+len(names)]]==names]
    if len(matches)!=1:raise RuntimeError('stock reputation rows do not uniquely identify the visible catalog slice')
    return [r['index'] for r in matches[0]]


def scroll(t,down,label,public,before):
    suffix='ScrollDownButton' if down else 'ScrollUpButton'
    def outcome(b,a,s):
        after=visible(controls(t),public);passed=bool(s and after and after!=before)
        oracle={'visible_indexes_before':before,'visible_indexes_after':after,'passed':passed}
        t.receipt.setdefault('reputation_scroll_oracles',{})[label]=oracle;t.persist()
        return {'status':'reputation_scroll_pass' if passed else 'client_or_protocol_failure','oracle':oracle}
    require(click_case(t,'reputation.scroll.'+label,'Scroll the reputation list '+('down' if down else 'up')+'.',
        lambda c:c['name']=='ReputationListScrollFrameScrollBar'+suffix,outcome),'reputation_scroll_pass')
    return t.receipt['reputation_scroll_oracles'][label]['visible_indexes_after']


@contextmanager
def revealed(t,row,public,label):
    original=visible(controls(t),public)
    if not original:raise RuntimeError('reputation viewport has no identifiable faction rows')
    current=original
    try:
        for attempt in range(32):
            if row['index'] in current:break
            current=scroll(t,row['index']>max(current),label+'_reveal_'+str(attempt),public,current)
        else:raise RuntimeError('faction did not become visible within bounded stock scrolling')
        yield
    finally:
        current=visible(controls(t),public)
        for attempt in range(32):
            if current==original:break
            current=scroll(t,min(current)<min(original),label+'_restore_'+str(attempt),public,current)
        else:raise RuntimeError('stock reputation viewport restoration exceeded its bound')
        t.receipt.setdefault('reputation_viewport_restoration',{})[label]={'before':original,'after':current,
            'passed':current==original};t.persist()
