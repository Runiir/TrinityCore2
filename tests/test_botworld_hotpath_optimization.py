from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text(encoding="utf-8")


def _persisted_diagnostic_samples(timestamps, heartbeat_ms=5000):
    """Counter model for the first-edge/heartbeat event contract."""
    persisted = 0
    suppressed = 0
    last_persisted = None
    for timestamp in timestamps:
        if last_persisted is not None and timestamp - last_persisted < heartbeat_ms:
            suppressed += 1
            continue
        persisted += 1
        last_persisted = timestamp
    return persisted, suppressed


def test_hotpath_uses_immutable_guid_index_and_edge_only_formation_payloads():
    assert "std::unordered_map<uint32, WorldBotState*> stateByGuid" in IMPLEMENTATION
    assert "stateByGuid.find(guid)" in IMPLEMENTATION
    assert "group->GetMemberGroup(bot->GetGUID()) != subgroup" in IMPLEMENTATION
    assert "bool const recordGroupFormation" in IMPLEMENTATION
    assert "if (recordGroupFormation || recordRaidFormation || recordRoleAssignment)" in IMPLEMENTATION


def test_hotpath_persists_fingerprint_deltas_and_dedupes_repeatable_diagnostics():
    assert "DecisionFingerprintPersistHeartbeatMs" in IMPLEMENTATION
    assert "repeat_count = repeat_count + VALUES(repeat_count)" in IMPLEMENTATION
    assert "failure_count = failure_count + VALUES(failure_count)" in IMPLEMENTATION
    assert "suppressed_count" in IMPLEMENTATION
    assert "dedupe_mode\\\":\\\"first_edge_heartbeat" in IMPLEMENTATION
    assert "LastPersistedDiagnosticDecisionKey" in IMPLEMENTATION

    persisted, suppressed = _persisted_diagnostic_samples([0, 1000, 2000, 4999, 5000, 6000])
    assert (persisted, suppressed) == (2, 4)


def test_hotpath_fingerprint_db_read_is_not_on_every_decision_tick():
    fingerprint = IMPLEMENTATION[
        IMPLEMENTATION.index("void BotWorldPopulationMgr::RecordDecisionFingerprintMemory") :
        IMPLEMENTATION.index("void BotWorldPopulationMgr::RecordDecisionTrace")
    ]
    assert fingerprint.count("PQuery(\"SELECT repeat_count, failure_count") == 1
    assert "if (!fingerprintChanged && !failureEdge && !heartbeatDue)" in fingerprint


def _record_fingerprint(state, fingerprint_hash, failure):
    changed = not state["initialized"] or state["hash"] != fingerprint_hash
    failure_edge = failure and (changed or not state["previous_failure"])
    if changed:
        state.update(
            hash=fingerprint_hash,
            repeat=0,
            failures=0,
            persisted_repeat=0,
            persisted_failures=0,
        )
    state["repeat"] += 1
    state["failures"] += int(failure)
    state["initialized"] = True
    state["previous_failure"] = failure
    repeat_delta = max(0, state["repeat"] - state["persisted_repeat"])
    failure_delta = max(0, state["failures"] - state["persisted_failures"])
    state["persisted_repeat"] = state["repeat"]
    state["persisted_failures"] = state["failures"]
    return failure_edge, repeat_delta, failure_delta


def test_hotpath_route_reset_clears_same_hash_persistence_baseline_without_underflow():
    state = {
        "initialized": True,
        "hash": 17,
        "repeat": 40,
        "failures": 4,
        "persisted_repeat": 40,
        "persisted_failures": 4,
        "previous_failure": False,
    }
    # ResetValidationRouteRuntimeState is required to clear every member of
    # this tuple, including the persisted baseline and result edge.
    reset_body = IMPLEMENTATION[IMPLEMENTATION.index("void BotWorldPopulationMgr::ResetValidationRouteRuntimeState") :]
    for assignment in (
        "state.DecisionFingerprintInitialized = false;",
        "state.LastDecisionFingerprintHash = 0;",
        "state.LastDecisionFingerprintRepeatCount = 0;",
        "state.LastDecisionFingerprintFailureCount = 0;",
        "state.LastDecisionFingerprintFailure = false;",
        "state.DecisionFingerprintSituation.clear();",
        "state.DecisionFingerprintAction.clear();",
        "state.DecisionFingerprintActivity.clear();",
        "state.DecisionFingerprintQuestId = 0;",
        "state.DecisionFingerprintClusterId = 0;",
        "state.DecisionFingerprintMapId = 0;",
        "state.DecisionFingerprintZoneId = 0;",
        "state.DecisionFingerprintAreaId = 0;",
        "state.LastDecisionFingerprintPersistMs = 0;",
        "state.LastDecisionFingerprintPersistedRepeatCount = 0;",
        "state.LastDecisionFingerprintPersistedFailureCount = 0;",
    ):
        assert assignment in reset_body

    state.update(
        initialized=False,
        hash=0,
        repeat=0,
        failures=0,
        persisted_repeat=0,
        persisted_failures=0,
        previous_failure=False,
    )
    failure_edge, repeat_delta, failure_delta = _record_fingerprint(state, 17, False)
    assert failure_edge is False
    assert (repeat_delta, failure_delta) == (1, 0)


def test_hotpath_failure_edge_is_success_to_failure_not_cumulative_count():
    state = {
        "initialized": False,
        "hash": 0,
        "repeat": 0,
        "failures": 0,
        "persisted_repeat": 0,
        "persisted_failures": 0,
        "previous_failure": False,
    }
    assert _record_fingerprint(state, 9, True)[0] is True
    assert _record_fingerprint(state, 9, True)[0] is False
    assert _record_fingerprint(state, 9, False)[0] is False
    # A later failure is an edge again even though cumulative failures > 0.
    assert _record_fingerprint(state, 9, True)[0] is True


def test_hotpath_stop_flushes_pending_tail_with_saturating_deltas():
    assert "void BotWorldPopulationMgr::FlushDecisionFingerprintMemory" in IMPLEMENTATION
    assert "PersistDecisionFingerprintDelta(state, bot, repeatDelta, failureDelta);" in IMPLEMENTATION
    assert "FlushPendingDecisionFingerprintMemory();" in IMPLEMENTATION
    state = {
        "initialized": True,
        "hash": 5,
        "repeat": 8,
        "failures": 3,
        "persisted_repeat": 5,
        "persisted_failures": 2,
        "previous_failure": True,
    }
    # A stop flushes exactly the tail and advances the baseline; no second
    # flush can duplicate it, while a stale baseline cannot underflow.
    repeat_delta = max(0, state["repeat"] - state["persisted_repeat"])
    failure_delta = max(0, state["failures"] - state["persisted_failures"])
    assert (repeat_delta, failure_delta) == (3, 1)
    state["persisted_repeat"] = state["repeat"]
    state["persisted_failures"] = state["failures"]
    assert (max(0, state["repeat"] - state["persisted_repeat"]), max(0, state["failures"] - state["persisted_failures"])) == (0, 0)


def test_hotpath_fingerprint_change_flushes_old_stream_before_replacing_identity():
    fingerprint = IMPLEMENTATION[
        IMPLEMENTATION.index("void BotWorldPopulationMgr::RecordDecisionFingerprintMemory") :
        IMPLEMENTATION.index("void BotWorldPopulationMgr::RecordDecisionTrace")
    ]
    flush_at = fingerprint.index("FlushDecisionFingerprintMemory(state, bot);")
    replace_at = fingerprint.index("state.LastDecisionFingerprintHash = fingerprintHash;")
    assert flush_at < replace_at

    state = {
        "initialized": False,
        "hash": None,
        "repeat": 0,
        "persisted_repeat": 0,
    }
    rows = {}

    def record(fingerprint_hash):
        changed = not state["initialized"] or state["hash"] != fingerprint_hash
        if changed:
            if state["initialized"]:
                pending = max(0, state["repeat"] - state["persisted_repeat"])
                rows[state["hash"]] = rows.get(state["hash"], 0) + pending
                state["persisted_repeat"] = state["repeat"]
            state.update(hash=fingerprint_hash, repeat=0, persisted_repeat=rows.get(fingerprint_hash, 0))
        state["repeat"] += 1
        # Fingerprint changes persist their first decision immediately.
        if changed:
            rows[fingerprint_hash] = rows.get(fingerprint_hash, 0) + state["repeat"] - state["persisted_repeat"]
            state["persisted_repeat"] = state["repeat"]
        state["initialized"] = True

    record("A")
    record("A")
    record("A")
    record("B")
    assert rows == {"A": 3, "B": 1}


def test_hotpath_destructive_lifecycles_flush_before_player_invalidation():
    stop_autonomy = IMPLEMENTATION[
        IMPLEMENTATION.index("void BotWorldPopulationMgr::StopAutonomy") :
        IMPLEMENTATION.index("void BotWorldPopulationMgr::Shutdown")
    ]
    shutdown = IMPLEMENTATION[
        IMPLEMENTATION.index("void BotWorldPopulationMgr::Shutdown") :
        IMPLEMENTATION.index("bool BotWorldPopulationMgr::SpawnAutonomyBots")
    ]
    assert stop_autonomy.index("FlushPendingDecisionFingerprintMemory();") < stop_autonomy.index("sBotMgr->RemoveWorldBot")
    assert shutdown.index("FlushPendingDecisionFingerprintMemory();") < shutdown.index("Party() = PartyRuntime();")

    replay = IMPLEMENTATION[
        IMPLEMENTATION.index("ReplayExecutionResult BotWorldPopulationMgr::ExecuteReplayRecord") :
        IMPLEMENTATION.index("std::string BotWorldPopulationMgr::BuildReplayResultJson")
    ]
    assert replay.index("FlushDecisionFingerprintMemory(Party().Bots.back(), bot);") < replay.index("sBotMgr->RemoveWorldBot(bot->GetGUID())")

    # Admission identity-drift, non-empty-start, and rollback cleanup all
    # retain state until the flush has occurred.
    admission = IMPLEMENTATION[IMPLEMENTATION.index("void BotWorldPopulationMgr::EnsurePopulation") :]
    assert admission.count("FlushPendingDecisionFingerprintMemory();") >= 3
