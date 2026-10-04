"""Attribute an owned peer's target before using the observed assist binding."""
import argparse
from pathlib import Path
from . import lab_runtime as lab
from .interaction_ground_movement import suite
from .interaction_targeting import target,selection
from .interaction_actionbar_pages import detail
from .interaction_trial import binding_key
from .observation.inventory import Inventory
from .interaction_social import actor


def phase(t,peer,oracle,session,peer_session):
    bar=detail(t,'assist_bindings');keys=bar['keys']
    if not keys.get('TARGETPARTYMEMBER1') or not keys.get('ASSISTTARGET'):
        raise RuntimeError('installed party/assist bindings are absent')
    other=Inventory(lab.ROOT,peer_session,peer.fixture['guid']).poll()
    # The previous actor's successful assist selects itself. Establish the
    # peer's target afresh for each phase through its stock party binding.
    with actor(peer.fixture['actor']):
        peer_keys=detail(peer,'assist_peer_bindings')['keys']
        target(peer,other,peer_session,'fixture.assist_peer_select_owner',
            {'kind':'key','value':binding_key(peer_keys['TARGETPARTYMEMBER1'][0]),'hold':.4},t.fixture['guid'])
    if selection(other)!=t.fixture['guid']:
        raise RuntimeError('owned peer does not have the staged actor selected')
    target(t,oracle,session,'fixture.assist_select_peer',
        {'kind':'key','value':binding_key(keys['TARGETPARTYMEMBER1'][0]),'hold':.4},peer.fixture['guid'])
    observed=detail(t,'assist_peer_target')['targeting']['units']
    checks={'native_peer_target':selection(other)==t.fixture['guid'],
        'public_target':observed['target']==peer.guid,'public_target_target':observed['targettarget']==t.guid}
    t.receipt['assist_target_attribution']={'checks':checks,'public':observed,
        'native_peer_target':selection(other),'expected_target_target':t.guid};t.persist()
    if not all(checks.values()):raise RuntimeError('native owned-peer target is missing from public target-of-target')
    target(t,oracle,session,'targeting.assist',
        {'kind':'key','value':binding_key(keys['ASSISTTARGET'][0]),'hold':.4},t.fixture['guid'])
    target(t,oracle,session,'fixture.target_peer_before_target_target',
        {'kind':'key','value':binding_key(keys['TARGETPARTYMEMBER1'][0]),'hold':.4},peer.fixture['guid'])
    observed=detail(t,'target_target_attribution')['targeting']['units']
    if selection(other)!=t.fixture['guid'] or observed['targettarget']!=t.guid:
        raise RuntimeError('owned peer target changed before target-of-target command')
    target(t,oracle,session,'targeting.target_target',
        {'kind':'chat','value':'/target [@targettarget]'},t.fixture['guid'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    suite(p.parse_args().output,work=phase,separated=True)
