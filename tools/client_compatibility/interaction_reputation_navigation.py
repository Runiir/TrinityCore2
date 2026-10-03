"""Reveal an inactive faction with stock headers, without changing reputation."""
from .interaction_reputation import catalog,detail,native_state,inspect_stormwind
from .interaction_operations import click_case
from .interaction_macros import require


def header_row(public,name):
    return next(r for r in public['rows'] if r['header'] and
        (r.get('id')==469 if name=='Alliance' else r['name']=='Inactive'))


def set_header(t,name,collapsed,label):
    before=catalog(t,'navigation_before_'+label);row=header_row(before,name)
    if row['collapsed']==collapsed:return before
    native=native_state()
    def outcome(b,a,s):
        probe=catalog(t,'navigation_after_'+label)
        passed=s and header_row(probe,name)['collapsed']==collapsed and native_state()==native
        oracle={'public':probe,'source_row':row,'native_unchanged':native_state()==native,'passed':bool(passed)}
        t.receipt.setdefault('navigation_oracles',{})[label]=oracle;t.persist()
        return {'status':'reputation_navigation_pass' if passed else 'client_or_protocol_failure','oracle':oracle}
    require(click_case(t,'reputation.navigation.'+label,('Collapse ' if collapsed else 'Expand ')+name+'.',
        lambda c:c['name']=='ReputationBar'+str(row['index'])+'ExpandOrCollapseButton',outcome),'reputation_navigation_pass')
    return t.receipt['navigation_oracles'][label]['public']


def select_inactive(t,native,label):
    # Folding Alliance keeps the Inactive header and one moved faction within
    # the unscrolled stock viewport. Restore this header after moving it back.
    set_header(t,'Alliance',True,label+'_alliance')
    public=set_header(t,'Inactive',False,label+'_inactive')
    inspect_stormwind(t,public,native,'reputation.inactive_reselect.'+label)
    probe=detail(t,'inactive_reselected_'+label)
    checked=next((r['checked'] for r in probe['controls'] if r['name']=='ReputationDetailInactiveCheckbox'),False)
    passed=probe.get('selected',{}).get('id')==72 and probe['selected'].get('inactive') and checked
    t.receipt.setdefault('inactive_visibility_oracles',{})[label]={'public':probe,'passed':bool(passed)};t.persist()
    if not passed:raise RuntimeError('reselected faction does not show inactive in its public detail')


def restore_headers(t,baseline,label):
    return set_header(t,'Alliance',header_row(baseline,'Alliance')['collapsed'],label+'_alliance')
