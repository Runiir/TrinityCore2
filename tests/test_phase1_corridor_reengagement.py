"""Adversarial contracts for the native BWD corridor reengagement guard."""

import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_MANAGER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"


def _retirement_decision(members, *, discovery_leg=False, anchor, radius=48.0):
    """Model the shared retirement invariant, without modeling combat/pathing.

    The native retirement pass must preserve an alive, natural, attackable
    member only when its GUID and entry are exact current-node declarations and
    it is inside that node's finite cluster contract.  Discovery and foreign or
    unbounded members remain eligible for stale retirement.
    """

    declared_guids = {27, 59, 60}
    declared_entries = {42649, 42362}
    retained = []
    for member in members:
        exact_current_member = (
            not discovery_leg
            and member["guid"] in declared_guids
            and member["entry"] in declared_entries
            and member["alive"]
            and member["natural"]
            and member["attackable"]
            and math.dist(member["position"], anchor) <= radius
        )
        if exact_current_member:
            retained.append(member["guid"])
    return retained


def _reengagement_decision(members, *, anchor, radius=48.0):
    """Model native target reacquisition after retirement preserves members."""

    candidates = []
    for member in members:
        if member["guid"] not in _retirement_decision(members, anchor=anchor, radius=radius):
            continue
        if not (member["alive"] and member["attackable"] and member["path"]):
            continue
        candidates.append(member)
    if candidates:
        return "reacquire", min(candidates, key=lambda member: member["guid"])["guid"]
    return "fail_closed", None


def _post_wipe_members(*, path=True):
    return [
        {
            "guid": 27,
            "entry": 42649,
            "alive": False,
            "natural": True,
            "attackable": False,
            "in_combat": False,
            "victim": False,
            "path": path,
            "position": (0.0, 0.0, 0.0),
            "home": (0.0, 0.0, 0.0),
        },
        {
            "guid": 59,
            "entry": 42362,
            "alive": True,
            "natural": True,
            "attackable": True,
            "in_combat": False,
            "victim": False,
            "path": path,
            "position": (-298.833, -50.349, 212.215),
            "home": (-298.833, -50.349, 212.298),
        },
        {
            "guid": 60,
            "entry": 42362,
            "alive": True,
            "natural": True,
            "attackable": True,
            "in_combat": False,
            "victim": False,
            "path": path,
            "position": (-307.913, -49.5694, 212.172),
            "home": (-307.913, -49.5694, 212.262),
        },
    ]


def test_post_wipe_reacquires_exact_live_drudge_at_cluster_boundary():
    decision, guid = _reengagement_decision(
        _post_wipe_members(),
        anchor=(-328.403, -88.0364, 213.964),
    )
    assert (decision, guid) == ("reacquire", 59)


def test_post_wipe_reengagement_fails_closed_without_native_path_or_identity():
    members = _post_wipe_members(path=False)
    members[1]["entry"] = 99999
    decision, guid = _reengagement_decision(
        members,
        anchor=(-328.403, -88.0364, 213.964),
    )
    assert (decision, guid) == ("fail_closed", None)


def test_all_survivor_recovery_keeps_exact_members_authoritative():
    members = _post_wipe_members()
    anchor = (-328.403, -88.0364, 213.964)
    for member in members:
        member["alive"] = True
        member["attackable"] = True
        member["position"] = anchor
        member["home"] = anchor
    assert _retirement_decision(
        members,
        anchor=anchor,
    ) == [27, 59, 60]


def test_discovery_or_unbounded_or_undeclared_member_is_not_sticky():
    members = _post_wipe_members()
    members[1]["entry"] = 99999
    members[1]["position"] = (-328.403, -88.0364, 213.964)
    assert _retirement_decision(
        members,
        anchor=(-328.403, -88.0364, 213.964),
    ) == [60]
    assert _retirement_decision(
        _post_wipe_members(),
        discovery_leg=True,
        anchor=(-328.403, -88.0364, 213.964),
    ) == []


def test_source_keeps_reengagement_narrow_and_preserves_route_gates():
    source = BOT_MANAGER.read_text(encoding="utf-8")
    marker = "bool const exactCurrentRouteMember"
    branch = source[source.index(marker) : source.index("auto activeValidationRoutePackTarget", source.index(marker))]
    assert "!discoveryLeg" in branch
    assert "isValidationRouteScriptTarget(creature)" in branch
    assert "hasStrictPathToValidationRouteTarget(creature)" not in branch
    script_target = source[source.index("auto isValidationRouteScriptTarget") : source.index("auto isValidationRouteCombatTarget")]
    assert "ValidationRouteClusterRadiusYards" in script_target
    assert "ValidationRoutePackMemberGuids.find(creature->GetGUID())" in script_target

    target = source[source.index("auto activeValidationRoutePackTarget") : source.index("auto isNaturalForwardHostile", source.index("auto activeValidationRoutePackTarget"))]
    assert "isValidationRoutePackEntry(creature->GetEntry())" in target
    assert "hasStrictPathToValidationRouteTarget(creature)" in target
    assert "ValidationRoutePackDeathGuids" in target

    route = (ROOT / "experiments/configs/validation_scenarios_cata_001.json").read_text(encoding="utf-8")
    assert '"source_entry": 42649' in route
    assert '"source_guid": "250050"' in route
    # Magmaw rehearsal keeps the Chainwielder and Drudge pair as separate
    # authoritative nodes.  Reengagement may retain the current node's exact
    # members, but it must never merge the next Drudge family into the
    # Chainwielder pack.
    assert '"pack_target_entries": [42649]' in route
    assert '"pack_target_entries": [42362]' in route
    chainwielder = route.index('"label": "Magmaw Chainwielder trash"')
    drudges = route.index('"label": "Magmaw Drudge pair"')
    assert chainwielder < drudges
    assert '"minimum_distance_source_entry": 42362' in route
    assert '"minimum_distance_yards": 15.0' in route
