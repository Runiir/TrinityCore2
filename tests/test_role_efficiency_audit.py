from pathlib import Path

from tools.bot_ml.audit_role_efficiency import build_audit
from tools.bot_ml.run_live_bot_validation import attach_stonecore_role_quality_audit


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
    assert "SET `min_range` = 10" in sql
    assert 'livingCombatResurrectionCaster = true' in manager
    assert '"tactical_retreat_no_combat_res"' in manager
    assert 'candidate.RejectReason = "target_immune"' in manager
    assert manager.count('candidate.RejectReason = "target_immune"') >= 3
    assert '"righteous_defense_party_pickup"' in manager
    assert "'rapid_fire,burn', 1.20" in sql
    assert "_validationRoutePackTransitionGuids.find(creature->GetGUID())" in manager
    for spell_id in (31850, 85673, 86150, 11129, 3045, 34490, 30823, 51533, 73680):
        assert str(spell_id) in sql


def test_role_audit_v3_requires_complete_rotations_pet_hazards_and_all_hostile_threat():
    roles = {
        "Scvaltank": (1, "survive_hold_threat_position_control_then_safe_dps", [53595, 26573, 31935, 53600]),
        "Scvalheal": (2, "keep_group_alive_triage_dispel_mana_efficiency_then_safe_dps", [2061]),
        "Scvaldpsa": (3, "maximize_safe_damage", [44457, 133, 92315, 11129]),
        "Scvaldpsb": (4, "maximize_safe_damage", [1978, 53209, 56641, 19434, 3045]),
        "Scvaldpsc": (5, "maximize_safe_damage", [17364, 60103, 8050, 73680, 403, 51533]),
    }
    entries = []
    sequence = 0
    for name, (guid, role_goal, spells) in roles.items():
        for spell in spells:
            sequence += 1
            entry = _entry(name, guid, sequence, role_goal, spell=spell, recorded=100 + sequence)
            entry["threat_snapshot"] = {
                "engaged_hostiles": 4,
                "tank_owned_hostiles": 4,
                "healer_targeting_hostiles": 0,
            }
            entry["pet_alive"] = name == "Scvaldpsb"
            if name == "Scvalheal":
                entry["combat_attempt"]["phase"] = "heal_cast"
            entries.append(entry)
    for offset in range(2):
        hazard = _entry("Scvaltank", 1, sequence + offset + 1, roles["Scvaltank"][1], spell=53595, recorded=1000 + offset)
        hazard["action"] = "move_out_of_hazard"
        hazard["threat_snapshot"] = {"engaged_hostiles": 4, "tank_owned_hostiles": 4, "healer_targeting_hostiles": 0}
        entries.append(hazard)

    audit = build_audit({"status": {"deaths": 0}, "trace": {"entries": entries}}, "abc")

    assert audit["schema"] == "stonecore_role_efficiency_v3"
    assert audit["passed"] is True
    assert audit["mechanics"]["hazard_exit_actions"] == 2


def test_role_audit_v3_rejects_observed_stonecore_quality_regressions():
    entries = []
    for index, (name, guid, role_goal) in enumerate(
        [
            ("Scvaltank", 1, "survive_hold_threat_position_control_then_safe_dps"),
            ("Scvalheal", 2, "keep_group_alive_triage_dispel_mana_efficiency_then_safe_dps"),
            ("Scvaldpsa", 3, "maximize_safe_damage"),
            ("Scvaldpsb", 4, "maximize_safe_damage"),
            ("Scvaldpsc", 5, "maximize_safe_damage"),
        ]
    ):
        entry = _entry(name, guid, index + 1, role_goal, spell=133, recorded=100 + index)
        entry["threat_snapshot"] = {"engaged_hostiles": 4, "tank_owned_hostiles": 2, "healer_targeting_hostiles": 2}
        entry["pet_alive"] = False
        entries.append(entry)

    audit = build_audit({"status": {"deaths": 1}, "trace": {"entries": entries}}, "abc")

    assert audit["passed"] is False
    assert "Scvaltank:all_hostile_threat_retention" in audit["failure_labels"]
    assert "Scvaltank:healer_target_exposure" in audit["failure_labels"]
    assert "Scvaldpsb:pet_alive_rate" in audit["failure_labels"]
    assert "party:hazard_activation_coverage" in audit["failure_labels"]


def test_role_audit_v3_scopes_pickup_grace_and_dwell_to_each_hostile_guid():
    entries = []
    snapshots = [
        (100, [101], [], [101]),
        (1100, [101], [], [101]),
        (2100, [101, 102], [101], [102]),
        (3100, [101, 102], [101], [102]),
        (4100, [101, 102], [101], [102]),
    ]
    for sequence, (timestamp, engaged, tank_owned, healer_targeting) in enumerate(snapshots, start=1):
        entry = _entry(
            "Scvaltank",
            1,
            sequence,
            "survive_hold_threat_position_control_then_safe_dps",
            spell=53595,
            recorded=timestamp,
        )
        entry["threat_snapshot"] = {
            "engaged_hostiles": len(engaged),
            "tank_owned_hostiles": len(tank_owned),
            "healer_targeting_hostiles": len(healer_targeting),
            "engaged_hostile_guids": engaged,
            "tank_owned_hostile_guids": tank_owned,
            "healer_targeting_hostile_guids": healer_targeting,
        }
        entries.append(entry)

    audit = build_audit({"status": {}, "trace": {"entries": entries}}, "abc")
    tank = next(bot for bot in audit["bots"] if bot["bot_name"] == "Scvaltank")

    assert tank["identity_scoped_threat"] is True
    assert tank["tank_all_hostile_retention_rate"] == 1.0
    assert tank["healer_target_exposure_rate"] == 0.0
    assert tank["max_healer_target_dwell_ms"] == 2000
    assert audit["mechanics"]["threat_acquisition_grace_ms"] == 3000


def test_full_stonecore_acceptance_is_revoked_when_role_quality_fails():
    report = {
        "all_passed": True,
        "acceptable_final_evidence": True,
        "failure_labels": [],
        "final_evidence_rejections": [],
        "status": {"deaths": 1},
        "trace": {"entries": []},
    }

    attach_stonecore_role_quality_audit(
        report,
        {"scenario_id": "stonecore_5n"},
        {"routes": [{"route_node_id": "entrance"}]},
    )

    assert report["role_efficiency_audit"]["passed"] is False
    assert report["all_passed"] is False
    assert report["acceptable_final_evidence"] is False
    assert "stonecore_role_quality_audit_failed" in report["failure_labels"]
    assert "stonecore_role_quality_audit_failed" in report["final_evidence_rejections"]


def test_stonecore_segment_diagnostics_do_not_run_full_clear_quality_gate():
    report = {"all_passed": True, "acceptable_final_evidence": True}

    attach_stonecore_role_quality_audit(
        report,
        {"scenario_id": "stonecore_5n", "segment_id": "corborus"},
        {"routes": [{"route_node_id": "corborus"}]},
    )

    assert "role_efficiency_audit" not in report
    assert report["all_passed"] is True
