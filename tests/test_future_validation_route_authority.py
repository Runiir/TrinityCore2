from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RECOVERY = (
    ROOT
    / "src/server/game/Bots/BotWorldPopulationMgrValidationRecoveryGate.cpp"
).read_text(encoding="utf-8")
AUTHORITY = (
    ROOT
    / "src/server/game/Bots/BotWorldPopulationMgrValidationAuthority.cpp"
).read_text(encoding="utf-8")


def _future_target_is_protected(
    manifest: list[dict],
    current_index: int,
    *,
    entry: int,
    spawn_id: int,
    raw_guid: int,
    enrolled_current_guids: set[int],
) -> bool:
    """Executable identity model for the manifest-owned C++ authority."""
    if raw_guid in enrolled_current_guids:
        return False
    for node in manifest[current_index + 1 :]:
        if node["kind"] not in {"trash", "boss"}:
            continue
        entries = {
            node.get("target_entry", 0),
            node.get("opener_target_entry", 0),
            *node.get("target_entries", []),
            *node.get("alternate_target_entries", []),
            *node.get("add_target_entries", []),
            *node.get("pack_target_entries", []),
            *node.get("scripted_event_entries", []),
        }
        spawns = {
            node.get("target_spawn_id", 0),
            *node.get("split_source_guids", []),
        }
        if entry in entries or spawn_id in spawns:
            return True
    return False


def test_chainwielder_protects_all_later_drudges_and_magmaw_targets():
    manifest = [
        {"kind": "trash", "target_entry": 42649},  # Chainwielder
        {
            "kind": "trash",
            "target_entry": 42362,
            "target_spawn_id": 250140,
            "split_source_guids": [250141],
        },  # Drudges
        {"kind": "boss", "target_entry": 41570},  # Magmaw
    ]

    # While Chainwielder is current, both the later Drudge spawn family and
    # the later Magmaw boss are protected, even though they are two identities
    # in different future nodes.
    assert _future_target_is_protected(
        manifest,
        0,
        entry=42362,
        spawn_id=250140,
        raw_guid=59,
        enrolled_current_guids={27},
    )
    assert _future_target_is_protected(
        manifest,
        0,
        entry=42362,
        spawn_id=250141,
        raw_guid=60,
        enrolled_current_guids={27},
    )
    assert _future_target_is_protected(
        manifest,
        0,
        entry=41570,
        spawn_id=0,
        raw_guid=39,
        enrolled_current_guids={27},
    )

    # Once Drudges are current, Magmaw remains protected by the later boss
    # node, while a current-generation GUID that reuses a future identity is
    # explicitly allowed by the authority precedence rule.
    assert _future_target_is_protected(
        manifest,
        1,
        entry=41570,
        spawn_id=0,
        raw_guid=39,
        enrolled_current_guids={59, 60},
    )
    assert not _future_target_is_protected(
        manifest,
        0,
        entry=42362,
        spawn_id=250140,
        raw_guid=27,
        enrolled_current_guids={27},
    )


def test_runtime_predicate_and_shared_authority_iterate_every_future_combat_node():
    helper = RECOVERY[
        RECOVERY.index(
            "bool BotWorldPopulationMgr::IsImmediateNextValidationRouteEncounterMember"
        ) : RECOVERY.index("bool BotWorldPopulationMgr::IsNativeRaidRecoveryEvidencePending")
    ]
    authority = AUTHORITY[
        AUTHORITY.index("std::vector<uint32> protectedEncounterEntries") : AUTHORITY.index(
            "BotRaidAreaAuthority::SetAllOffenseSuppressed"
        )
    ]

    for source in (helper, authority):
        assert "for (size_t routeIndex =" in source
        assert "routeIndex < Party().ValidationRouteManifest.size()" in source
        assert 'nextNode.Kind != "boss" && nextNode.Kind != "trash"' in source
        assert "nextNode.TargetEntries" in source
        assert "nextNode.AddTargetEntries" in source
        assert "nextNode.PackTargetEntries" in source
        assert "nextNode.ScriptedEventEntries" in source
        assert "nextNode.SplitSourceGuids" in source

    assert "Party().ValidationRoutePackMemberGuids.find(creature->GetGUID())" in helper
    assert "SetAllowedEncounterGuids" in authority
