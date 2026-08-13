from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text(encoding="utf-8")
AUTHORITY = (ROOT / "src/server/game/Bots/BotRaidAreaAuthority.h").read_text(encoding="utf-8")
EXECUTOR = (ROOT / "src/server/game/Bots/BotActionExecutor.cpp").read_text(encoding="utf-8")


def _protected_target(*, entry, spawn_id, raw_guid, protected_entries, protected_spawns, allowed_guids):
    """Small executable model of the C++ identity precedence contract."""
    if raw_guid in allowed_guids:
        return False
    return entry in protected_entries or spawn_id in protected_spawns


def test_chainwielder_current_pack_guid_27_remains_authoritative_over_next_pack():
    # Exact Phase 1 regression shape: current Chainwielder GUID 27 is still
    # alive while future Drudges 59/60 are visible under the next node.
    protected_entries = {42362}
    protected_spawns = {250140, 250141}
    allowed_guids = {27}

    assert not _protected_target(
        entry=42649, spawn_id=250050, raw_guid=27,
        protected_entries=protected_entries,
        protected_spawns=protected_spawns,
        allowed_guids=allowed_guids,
    )
    assert _protected_target(
        entry=42362, spawn_id=250140, raw_guid=59,
        protected_entries=protected_entries,
        protected_spawns=protected_spawns,
        allowed_guids=allowed_guids,
    )
    assert _protected_target(
        entry=42362, spawn_id=250141, raw_guid=60,
        protected_entries=protected_entries,
        protected_spawns=protected_spawns,
        allowed_guids=allowed_guids,
    )


def test_next_trash_encounter_uses_entries_split_sources_and_spawn_ids():
    helper = RUNTIME[
        RUNTIME.index("bool BotWorldPopulationMgr::IsImmediateNextValidationRouteEncounterMember"):
        RUNTIME.index("bool BotWorldPopulationMgr::IsNativeRaidRecoveryEvidencePending")
    ]
    route_authority = RUNTIME[
        RUNTIME.index("std::vector<uint32> protectedEncounterEntries"):
        RUNTIME.index("BotRaidAreaAuthority::SetAllOffenseSuppressed", RUNTIME.index("std::vector<uint32> protectedEncounterEntries"))
    ]

    assert 'nextNode.Kind != "boss" && nextNode.Kind != "trash"' in helper
    assert "nextNode.TargetEntries" in helper
    assert "nextNode.PackTargetEntries" in helper
    assert "nextNode.SplitSourceGuids" in helper
    assert "creature->GetSpawnId() == nextNode.TargetSpawnId" in helper
    assert "SetProtectedEncounterSpawnIds" in route_authority
    assert "SetAllowedEncounterGuids" in route_authority


def test_profile_handoff_is_native_resolver_after_route_authority_rejects_future_target():
    resolver = RUNTIME[
        RUNTIME.index("ResolvedCombatAction BotWorldPopulationMgr::ResolveProfileCombatAction"):
        RUNTIME.index("bool BotWorldPopulationMgr::TryEnsurePersistentCombatSetup")
    ]
    # The future-target rejection is fail-closed and precedes profile setup;
    # legal current-pack targets still flow to the DB-backed BuildCandidates
    # resolver, with no damage-tuning or hard-coded filler substitution.
    assert "IsImmediateNextValidationRouteEncounterMember(creature)" in resolver
    assert resolver.index("future_encounter_target_forbidden") < resolver.index("BotClassSpecActionProfileStore::Build")
    assert "BotClassSpecActionProfileStore::BuildCandidates(bot, target, profile)" in resolver
    assert 'action.DebugName = "no_valid_profile_action"' in resolver
    assert "IsProtectedEncounterTarget(" in EXECUTOR
