from pathlib import Path

from tools.bot_ml.audit_role_efficiency import build_audit
from tools.bot_ml.live_validation_session import acceptance_facts_from_report, evaluate_acceptance
from tools.bot_ml.run_live_bot_validation import attach_stonecore_role_quality_audit, compact_published_report


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
    assert "HandlePetActionHelper" in executor
    assert "AI()->AttackStart" not in executor
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
    assert '"tank_immediate_aoe_threat"' in manager
    assert '"tank_hazard_hold_aoe_threat"' in manager
    assert '"healer_stack_for_swarm_pickup"' in manager
    assert (
        'if (std::string(GetDungeonRole(bot)) == "tank")\n'
        '    {\n'
        '        Player* defenseTarget = nullptr;'
    ) in manager
    assert "'rapid_fire,burn', 1.20" in sql
    assert "Party().ValidationRoutePackTransitionGuids.find(creature->GetGUID())" in manager
    for spell_id in (31850, 85673, 86150, 11129, 3045, 34490, 30823, 51533, 73680):
        assert str(spell_id) in sql


def test_role_audit_v3_requires_complete_rotations_pet_hazards_and_all_hostile_threat():
    roles = {
        "Scvaltank": (1, "survive_hold_threat_position_control_then_safe_dps", [53595, 26573, 31935, 53600]),
        "Scvalheal": (2, "keep_group_alive_triage_dispel_mana_efficiency_then_safe_dps", [2061]),
        "Scvaldpsa": (3, "maximize_safe_damage", [44457, 133, 2120, 11129]),
        "Scvaldpsb": (4, "maximize_safe_damage", [53301, 1978, 3674, 77767, 2643, 3045]),
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
                "tank_threat_aura_active": True,
            }
            entry["pet_alive"] = name == "Scvaldpsb"
            if name == "Scvalheal":
                entry["combat_attempt"]["phase"] = "heal_cast"
            entries.append(entry)
    for offset in range(2):
        hazard = _entry("Scvaltank", 1, sequence + offset + 1, roles["Scvaltank"][1], spell=53595, recorded=1000 + offset)
        hazard["action"] = "move_out_of_hazard"
        hazard["threat_snapshot"] = {
            "engaged_hostiles": 4,
            "tank_owned_hostiles": 4,
            "healer_targeting_hostiles": 0,
            "tank_threat_aura_active": True,
        }
        entries.append(hazard)
    aoe_misdirection = _entry("Scvaldpsb", 4, sequence + 3, roles["Scvaldpsb"][1], spell=2643, recorded=1100)
    aoe_misdirection["action"] = "misdirection_aoe_transfer"
    entries.append(aoe_misdirection)

    audit = build_audit({"status": {"deaths": 0}, "trace": {"entries": entries}}, "abc")

    assert audit["schema"] == "stonecore_role_efficiency_v3"
    assert audit["passed"] is True
    assert audit["mechanics"]["hazard_exit_actions"] == 2
    assert audit["mechanics"]["misdirection_aoe_successes"] == 1


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
        entry["threat_snapshot"] = {
            "engaged_hostiles": 4,
            "tank_owned_hostiles": 2,
            "healer_targeting_hostiles": 2,
            "tank_threat_aura_active": False,
        }
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
            "tank_threat_aura_active": True,
        }
        entries.append(entry)

    audit = build_audit({"status": {}, "trace": {"entries": entries}}, "abc")
    tank = next(bot for bot in audit["bots"] if bot["bot_name"] == "Scvaltank")

    assert tank["identity_scoped_threat"] is True
    assert tank["tank_threat_aura_uptime_rate"] == 1.0
    assert tank["tank_all_hostile_retention_rate"] == 1.0
    assert tank["healer_target_exposure_rate"] == 0.0
    assert tank["max_healer_target_dwell_ms"] == 2000
    assert audit["mechanics"]["threat_acquisition_grace_ms"] == 3000


def test_role_audit_v3_rejects_missing_tank_threat_aura_during_combat():
    entry = _entry(
        "Scvaltank",
        1,
        1,
        "survive_hold_threat_position_control_then_safe_dps",
        spell=53595,
        recorded=100,
    )
    entry["threat_snapshot"] = {
        "engaged_hostiles": 1,
        "tank_owned_hostiles": 1,
        "healer_targeting_hostiles": 0,
        "tank_threat_aura_active": False,
    }

    audit = build_audit({"status": {}, "trace": {"entries": [entry]}}, "abc")

    tank = next(bot for bot in audit["bots"] if bot["bot_name"] == "Scvaltank")
    assert tank["tank_threat_aura_uptime_rate"] == 0.0
    assert "Scvaltank:tank_threat_aura_uptime" in audit["failure_labels"]


def _strict_stonecore_manifest_and_evidence():
    routes = [
        {
            "route_node_id": f"stonecore_node_{generation}",
            "route_generation": generation,
            "kind": "boss" if generation in {2, 5, 9, 14} else "trash",
        }
        for generation in range(1, 15)
    ]
    evidence = {
        "manifest_completion_evidence": {"route_generation": 14},
        "route_terminal_evidence": [
            {
                "route_node_id": route["route_node_id"],
                "route_generation": route["route_generation"],
            }
            for route in routes
        ],
        "real_boss_kill_evidence": [
            {
                "route_node_id": route["route_node_id"],
                "route_generation": route["route_generation"],
            }
            for route in routes
            if route["kind"] == "boss"
        ],
        "forbidden_completion_assists": [],
    }
    return {"routes": routes}, evidence


def test_full_stonecore_boss_clear_keeps_failed_role_quality_as_diagnostic():
    manifest, evidence = _strict_stonecore_manifest_and_evidence()
    report = {
        "all_passed": True,
        "acceptable_final_evidence": True,
        "failure_labels": [],
        "final_evidence_rejections": [],
        "returncode": 0,
        "timed_out": False,
        "completion_reason": "validation_route_manifest_complete",
        "evidence": evidence,
        "stages": [{"stage": "stonecore", "missing": []}],
        "validation_context": {"scenario_id": "stonecore_5n"},
        "validation_route_manifest": manifest,
        "watchdog_state": {},
        "status": {"deaths": 1},
        "trace": {"entries": []},
    }

    attach_stonecore_role_quality_audit(
        report,
        {"scenario_id": "stonecore_5n"},
        manifest,
    )

    assert report["role_efficiency_audit"]["passed"] is False
    assert report["role_efficiency_audit"]["enforcement"] == "advisory"
    assert report["role_efficiency_audit"]["authoritative_boss_clear"] is True
    assert report["role_quality_advisory_labels"]
    assert report["all_passed"] is True
    assert report["acceptable_final_evidence"] is True
    assert report["failure_labels"] == []
    assert report["final_evidence_rejections"] == []
    facts = acceptance_facts_from_report(report)
    assert facts["role_quality_audit_failed"] is True
    acceptance = evaluate_acceptance(facts)
    assert acceptance["accepted"] is True
    assert acceptance["authoritative_stonecore_boss_clear"] is True
    assert acceptance["role_quality_advisory"] is True
    compact = compact_published_report(report)
    assert compact["role_efficiency_audit"]["enforcement"] == "advisory"
    assert compact["role_quality_advisory_labels"] == report["role_quality_advisory_labels"]


def test_incomplete_stonecore_clear_still_enforces_failed_role_quality():
    manifest, evidence = _strict_stonecore_manifest_and_evidence()
    evidence["real_boss_kill_evidence"] = evidence["real_boss_kill_evidence"][:-1]
    report = {
        "all_passed": False,
        "acceptable_final_evidence": False,
        "failure_labels": [],
        "final_evidence_rejections": ["missing_real_boss_kill_evidence"],
        "returncode": 0,
        "timed_out": False,
        "evidence": evidence,
        "watchdog_state": {},
        "status": {"deaths": 1},
        "trace": {"entries": []},
    }

    attach_stonecore_role_quality_audit(
        report,
        {"scenario_id": "stonecore_5n"},
        manifest,
    )

    assert report["role_efficiency_audit"]["enforcement"] == "required"
    assert report["role_efficiency_audit"]["authoritative_boss_clear"] is False
    assert report["all_passed"] is False
    assert report["acceptable_final_evidence"] is False
    assert "stonecore_role_quality_audit_failed" in report["failure_labels"]
    assert "stonecore_role_quality_audit_failed" in report["final_evidence_rejections"]
    assert acceptance_facts_from_report(report)["role_quality_audit_failed"] is True


def test_stonecore_segment_diagnostics_do_not_run_full_clear_quality_gate():
    report = {"all_passed": True, "acceptable_final_evidence": True}

    attach_stonecore_role_quality_audit(
        report,
        {"scenario_id": "stonecore_5n", "segment_id": "corborus"},
        {"routes": [{"route_node_id": "corborus"}]},
    )

    assert "role_efficiency_audit" not in report
    assert report["all_passed"] is True
