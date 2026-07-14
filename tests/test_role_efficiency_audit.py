from pathlib import Path

from tools.bot_ml.audit_role_efficiency import build_audit


def _entry(name, guid, sequence, role_goal, result="ok", spell=1, recorded=100):
    return {
        "bot_name": name,
        "bot_guid": guid,
        "sequence": sequence,
        "timestamp_ms": recorded,
        "role_goal": role_goal,
        "action": "validation_route_trash_action",
        "combat_attempt": {
            "recorded_at_ms": recorded,
            "phase": "cast",
            "action": {"spell_id": spell},
            "failure": {"result": result},
            "uptime": {"melee_auto_attacking": True},
        },
        "route_progress": {
            "target": {"hp_pct": 0.5},
            "state": {"victim_guid": guid},
        },
    }


def test_role_audit_deduplicates_cumulative_trace_and_measures_roles():
    tank = _entry("tank", 1, 1, "survive_hold_threat_position_control_then_safe_dps")
    healer = _entry("heal", 2, 1, "keep_group_alive_triage_dispel_mana_efficiency_then_safe_dps")
    healer["combat_attempt"]["phase"] = "heal_cast"
    dps = [_entry(f"dps{i}", 3 + i, 1, "maximize_safe_damage", recorded=100 + i) for i in range(3)]
    entries = [tank, tank.copy(), healer, *dps]
    report = {"status": {"duration_seconds": 10, "kills": 1, "deaths": 0}, "trace": {"entries": entries}}

    audit = build_audit(report, "abc")

    assert audit["passed"] is True
    assert len(audit["bots"]) == 5
    assert next(bot for bot in audit["bots"] if bot["role"] == "tank")["tank_threat_retention_rate"] == 1.0
    assert next(bot for bot in audit["bots"] if bot["role"] == "healer")["heal_cast_success_rate"] == 1.0


def test_role_audit_rejects_failed_or_idle_rotation():
    entries = [
        _entry("tank", 1, 1, "survive_hold_threat_position_control_then_safe_dps", result="cast_failed"),
        _entry("heal", 2, 1, "keep_group_alive_triage_dispel_mana_efficiency_then_safe_dps", result="cast_failed"),
        *[_entry(f"dps{i}", 3 + i, 1, "maximize_safe_damage", result="no_action", recorded=100 + i) for i in range(3)],
    ]
    entries[1]["combat_attempt"]["phase"] = "heal_cast"
    for entry in entries[2:]:
        entry["combat_attempt"]["uptime"]["melee_auto_attacking"] = False
    report = {"status": {}, "trace": {"entries": entries}}

    audit = build_audit(report, "abc")

    assert audit["passed"] is False
    assert any(label.endswith("cast_failure_rate") for label in audit["failure_labels"])
    assert any(label.endswith("active_action_coverage") for label in audit["failure_labels"])


def test_role_audit_credits_passive_damage_uptime_during_spell_idle_ticks():
    entries = [
        _entry(f"dps{i}", 3 + i, 1, "maximize_safe_damage", result="no_action", recorded=100 + i)
        for i in range(3)
    ]
    report = {"status": {}, "trace": {"entries": entries}}

    audit = build_audit(report, "abc")

    for bot in audit["bots"]:
        assert bot["active_action_coverage"] == 1.0


def test_stonecore_role_profiles_include_runtime_efficiency_gates():
    root = Path(__file__).resolve().parents[1]
    manager = (root / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text()
    executor = (root / "src/server/game/Bots/BotActionExecutor.cpp").read_text()
    sql = (root / "sql/custom/world/2026_07_14_01_stonecore_role_efficiency.sql").read_text()

    assert 'candidate.RejectReason = "target_not_interruptible"' in manager
    assert 'candidate.RejectReason = "mana_gate"' in manager
    assert 'candidate.RejectReason = "insufficient_self_aura_stacks"' in manager
    assert "UnitHealthPct(tankTarget) <= 0.60f" in manager
    assert 'action.AutoAttackMode == "ranged"' in executor
    assert "TARGET_FLAG_DEST_LOCATION" in executor
    assert "pet->AI()->AttackStart(target)" in executor
    assert "a.`required_self_aura_stacks` = 5" in sql
    assert "a.`requires_interruptible_target` = 1" in sql
    assert "a.`required_target_aura` = 1978" in sql
    assert "a.`damage_weight` = 0.55, a.`min_enemies` = 5" in sql
    assert "a.`spell_id` = 26573" in sql
    assert "SET `min_range` = 8" in sql
    assert 'livingCombatResurrectionCaster = true' in manager
    assert '"tactical_retreat_no_combat_res"' in manager
    for spell_id in (31850, 85673, 86150, 11129, 3045, 34490, 30823, 51533, 73680):
        assert str(spell_id) in sql
