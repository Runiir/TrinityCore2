from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _runtime_source(module):
    return (ROOT / f"src/server/game/Bots/BotWorldPopulationMgr{module}.cpp").read_text(encoding="utf-8")


RECOVERY_GATE = _runtime_source("ValidationRecoveryGate")
ROUTE_AUTHORITY = _runtime_source("ValidationAuthority")
COMBAT_RESOLVER = _runtime_source("CombatResolver")
ROUTE_MANIFEST = _runtime_source("ValidationRouteManifest")
ROUTE_RUNTIME = _runtime_source("ValidationRouteRuntime")
VALIDATION_PROFILE = _runtime_source("ValidationProfile")
TERMINAL_ARRIVAL = _runtime_source("ValidationRouteTerminalArrival")
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
    helper = RECOVERY_GATE[
        RECOVERY_GATE.index("bool BotWorldPopulationMgr::IsImmediateNextValidationRouteEncounterMember"):
        RECOVERY_GATE.index("bool BotWorldPopulationMgr::IsNativeRaidRecoveryEvidencePending")
    ]
    route_authority = ROUTE_AUTHORITY[
        ROUTE_AUTHORITY.index("std::vector<uint32> protectedEncounterEntries"):
        ROUTE_AUTHORITY.index("BotRaidAreaAuthority::SetAllOffenseSuppressed", ROUTE_AUTHORITY.index("std::vector<uint32> protectedEncounterEntries"))
    ]

    assert 'nextNode.Kind != "boss" && nextNode.Kind != "trash"' in helper
    assert "nextNode.TargetEntries" in helper
    assert "nextNode.PackTargetEntries" in helper
    assert "nextNode.SplitSourceGuids" in helper
    assert "uint32 const spawnId = creature->GetSpawnId();" in helper
    assert "nextNode.TargetSpawnId && spawnId == nextNode.TargetSpawnId" in helper
    assert "SetProtectedEncounterSpawnIds" in route_authority
    assert "SetAllowedEncounterGuids" in route_authority


def test_profile_handoff_is_native_resolver_after_route_authority_rejects_future_target():
    # ResolveProfileCombatAction is the last function in its split owner.
    resolver = COMBAT_RESOLVER[
        COMBAT_RESOLVER.index("ResolvedCombatAction BotWorldPopulationMgr::ResolveProfileCombatAction"):
    ]
    # The future-target rejection is fail-closed and precedes profile setup;
    # legal current-pack targets still flow to the DB-backed BuildCandidates
    # resolver, with no damage-tuning or hard-coded filler substitution.
    assert "IsImmediateNextValidationRouteEncounterMember(creature)" in resolver
    assert resolver.index("future_encounter_target_forbidden") < resolver.index("BotClassSpecActionProfileStore::Build")
    assert "BotClassSpecActionProfileStore::BuildCandidates(bot, target, profile)" in resolver
    assert 'action.DebugName = "no_valid_profile_action"' in resolver
    assert "IsProtectedEncounterTarget(" in EXECUTOR


def test_current_generation_guid_wins_when_next_node_reuses_identity_family():
    helper = RECOVERY_GATE[
        RECOVERY_GATE.index("bool BotWorldPopulationMgr::IsImmediateNextValidationRouteEncounterMember"):
        RECOVERY_GATE.index("bool BotWorldPopulationMgr::IsNativeRaidRecoveryEvidencePending")
    ]
    # H5: the current exact GUID remains legal even when entry/spawn identity
    # overlaps the next node. Transition/death exclusions precede this guard.
    assert "if (persistedCurrentMember)" in helper
    assert "if (persistedCurrentMember && !nextEntry && !nextSpawn)" not in helper


def test_nefarian_descent_fails_closed_without_synthetic_jump_or_position_assistance():
    # The arrival branch is now the final branch of its split owner.
    descent = TERMINAL_ARRIVAL[TERMINAL_ARRIVAL.index('if (Manager.Cohort().Config.ValidationRouteKind == "descent"\n            && !Manager.Cohort().Config.ValidationRouteDescentAction.empty())'):]
    assert 'node.DescentAction = ExtractJsonStringField(routeJson, "descent_action")' in ROUTE_MANIFEST
    assert 'Cohort().Config.ValidationRouteDescentAction = node.DescentAction' in ROUTE_RUNTIME
    assert 'native_descent_semantics_unavailable' in descent
    assert 'validation_route_descent_blocked' in descent
    assert 'MoveJump(' not in descent
    assert 'TeleportTo(' not in descent
    assert 'bool const moved = Callbacks.MoveToRouteAnchor();' in descent


def test_diagnostic_profile_and_pool_admission_are_manifest_owned_and_exact():
    profile_start = VALIDATION_PROFILE.index("bool BotWorldPopulationMgr::IsValidationProfileName")
    prepare_start = VALIDATION_PROFILE.index("std::string BotWorldPopulationMgr::PrepareValidationProfile", profile_start)
    prepare_end = VALIDATION_PROFILE.index("bool BotWorldPopulationMgr::PrepareCurrentValidationProfile", prepare_start)
    reset_start = VALIDATION_PROFILE.index("bool BotWorldPopulationMgr::ResetValidationBotPool")
    reset_end = len(VALIDATION_PROFILE)  # ResetValidationBotPool ends this module.
    profile = VALIDATION_PROFILE[
        profile_start:prepare_start
    ]
    prepare = VALIDATION_PROFILE[
        prepare_start:prepare_end
    ]
    reset = VALIDATION_PROFILE[
        reset_start:reset_end
    ]
    assert "RuntimeProfiles.find(name)" in profile
    assert "candidate.Config.ValidationRouteScenarioId == name" in profile
    assert "candidate.Config.PoolTagFilter == name" in profile
    assert 'manifest_runtime_profile_identity_mismatch' in ROUTE_MANIFEST
    assert 'pool_tag_profile_mismatch' in prepare
    assert 'validation_pool_exact_size_mismatch' in reset
    assert 'validation_pool_exact_raid_composition_mismatch' in reset
    assert 'experiment_tags` = ' in reset
