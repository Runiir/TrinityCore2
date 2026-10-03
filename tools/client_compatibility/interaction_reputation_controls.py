"""Reversible stock reputation watch and header clicks; no privileged mutations."""
from .interaction_reputation import detail,catalog,native_state
from .interaction_operations import click_case
from .interaction_macros import require


def watch(t,enabled,label,baseline,faction):
    def outcome(b,a,s):
        probe=detail(t,'watch_'+label);actual=native_state()
        expected={**baseline,'character':(*baseline['character'][:2],faction['index'] if enabled else 0xffffffff)}
        shown=next(r['visible'] for r in probe['controls'] if r['name']=='ReputationWatchBar')
        public=probe.get('watched',{});selected=probe.get('selected',{})
        public_ok=(public.get('id'),public.get('value'))==(72,faction['value']) if enabled else not public.get('name')
        bar=probe.get('watch_bar',{})
        bar_ok=not enabled or (bar.get('min'),bar.get('max'),bar.get('value'))==(
            0,selected['max']-selected['min'],faction['value']-selected['min'])
        passed=s and selected.get('id')==72 and selected.get('watched')==enabled and shown==enabled and public_ok and bar_ok and actual==expected
        oracle={'public':probe,'native':actual,'expected_native':expected,'passed':bool(passed)}
        t.receipt.setdefault('watch_oracles',{})[label]=oracle;t.persist()
        return {'status':'reputation_watch_pass' if passed else 'client_or_protocol_failure','oracle':oracle}
    require(click_case(t,'reputation.watch.'+label,('Show' if enabled else 'Hide')+' Stormwind on the main screen.',
        lambda c:c['name']=='ReputationDetailMainScreenCheckbox',outcome),'reputation_watch_pass')


def comparable(rows):
    return [{k:v for k,v in r.items() if k!='index'} for r in rows]


def header(t,collapsed,label,baseline):
    row=next(r for r in baseline['rows'] if r.get('id')==469)
    if row['collapsed']:raise RuntimeError('requires the initially expanded Alliance header')
    def outcome(b,a,s):
        probe=catalog(t,'header_'+label);current=next(r for r in probe['rows'] if r.get('id')==469)
        removed=[r['id'] for r in baseline['rows'] if r['index']>row['index']]
        expected=[{**r,'collapsed':True} if r.get('id')==469 else r for r in baseline['rows'] if
            not collapsed or r['index']<=row['index']]
        passed=s and current['collapsed']==collapsed and comparable(probe['rows'])==comparable(expected)
        oracle={'public':probe,'hidden_ids':removed if collapsed else [],'passed':bool(passed)}
        t.receipt.setdefault('header_oracles',{})[label]=oracle;t.persist()
        return {'status':'reputation_header_pass' if passed else 'client_or_protocol_failure','oracle':oracle}
    require(click_case(t,'reputation.header.'+label,('Collapse' if collapsed else 'Expand')+' the Alliance reputation header.',
        lambda c:c['name']=='ReputationBar'+str(row['index'])+'ExpandOrCollapseButton',outcome),'reputation_header_pass')


def suite_controls(t,public,before,native):
    if before['character'][2]!=0xffffffff:raise RuntimeError('watch trial requires no previously watched faction')
    try:
        watch(t,True,'show',before,native[72]);watch(t,False,'hide',before,native[72])
        header(t,True,'collapse',public);header(t,False,'expand',public)
    finally:
        current=native_state()
        if current['character'][2]!=before['character'][2]:watch(t,False,'cleanup_hide',before,native[72])
        probe=catalog(t,'controls_restoration');row=next(r for r in probe['rows'] if r.get('id')==469)
        if row['collapsed']:header(t,False,'cleanup_expand',public);probe=catalog(t,'controls_restored')
        passed=comparable(probe['rows'])==comparable(public['rows'])
        t.receipt['controls_restoration']={'catalog_restored':passed};t.persist()
        if not passed:raise RuntimeError('reputation controls did not restore the public catalog')
