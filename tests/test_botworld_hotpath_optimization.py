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
