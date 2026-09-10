import base64
import json

from tools.raid_program.bot_timeline import build_timeline_from_rows
from tools.raid_program.bot_timeline_html import render_timeline_html


IDENTITY = {"cohort_id": "raid", "server_epoch": 11, "attempt_id": 2}
PROFILE = {"profile_generation": 8, "profile_content_hash": "profile-hash"}


def _bound(channel, payload):
    return {"normalized_schema_version": 2, "evidence_channel": channel,
            "identity_binding": {"state": "bound", "canonical_identity_sha256": "a" * 64},
            "payload": payload}


def _event(sequence, at, *, effect=1, amount=10, pet=False, target=41570):
    return {"event_sequence": sequence, "timestamp_ms": at, "route_generation": 4,
            "kind": "damage", "actor_guid": 7, "actor_name": "Mage", "actor_role": "dps",
            "actor_class_id": 8, "source_guid": 70 if pet else 7, "source_entry": 1 if pet else 0,
            "source_is_pet": pet, "target_guid": 99, "target_entry": target,
            "spell_id": 100 + effect, "effect_type": effect, "originated_amount": amount}


def _ability(event, perspective="damage_done"):
    return {**{key: event[key] for key in ("route_generation", "actor_guid", "source_entry", "spell_id", "target_entry", "effect_type")},
            "perspective": perspective}


def _full(events):
    return {"ok": True, "action": "botauto_combatlog", "combat_log_schema_version": 3,
            "damage_attribution_schema": "originated_amount_v2_friendly_split", **IDENTITY,
            "combat_log_epoch": 3, **PROFILE, "event_count": max((e["event_sequence"] for e in events), default=0),
            "abilities": [_ability(e) for e in events], "recent_events": events}


def _delta_frames(events, before, after):
    payload = {"ok": True, "action": "botauto_combatlog_delta", "combat_log_schema_version": 3,
               **IDENTITY, "combat_log_epoch": 3, **PROFILE, "event_count_at_export": after,
               "cursor_before": before, "cursor_after": after, "gap": False, "recent_events": events}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    envelope = {**IDENTITY, "combat_log_chunk_schema_version": 1, "export_id": after,
                "export_kind": "delta", "chunk_count": 1}
    return [{**envelope, "action": "botauto_combatlog_chunk", "sequence": 0,
             "encoding": "base64", "data": base64.b64encode(raw).decode()},
            {**envelope, "action": "botauto_combatlog_complete", "total_bytes": len(raw)}]


def _trace(entries, **identity):
    return {"action": "botauto_trace", **(identity or IDENTITY), "bots": [{"bot_guid": 7, "bot_name": "Mage", "entries": entries}]}


def _report(failed=False):
    return {"classification": "failure" if failed else "success", "terminal_failure": {"detected": failed},
            "development_run": {"native_boss_death_accepted": not failed,
                                "accepted_boss_identity": {"target_entry": 41570}},
            "evidence_demux": {"canonical_identity_sha256": "a" * 64},
            "combat_log_event_stream": {"identity": {**IDENTITY, "combat_log_epoch": 3},
                                        "profile_context": PROFILE, "gap_ranges": []}}


def test_join_deduplicates_snapshots_isolates_identity_and_marks_legacy_fields():
    legacy = {"timestamp_ms": 1000, "sequence": 1, "action": "wait", "result": "idle",
              "action_category": "current_export_state", "movement_planner": {"moving": True}}
    death = {"timestamp_ms": 9000, "sequence": 2, "action": "boss_killed",
             "result": "confirmed_unit_death", "target": {"entry": 41570}}
    foreign = _trace([{**legacy, "sequence": 4}], cohort_id="other", server_epoch=12, attempt_id=2)
    landed = _event(1, 1000)
    rows = [_bound("trace", _trace([legacy, death])), _bound("trace", _trace([legacy, death])),
            _bound("trace", foreign), _bound("combat_log", _full([landed]))]
    model, summary = build_timeline_from_rows(rows, _report())
    assert summary["completeness"]["trace_entry_count"] == 2
    assert summary["completeness"]["identity_rejections"][0]["identity"]["cohort_id"] == "other"
    assert summary["completeness"]["legacy_historical_metadata_warning"]
    assert not [event for event in model["events"] if event["kind"] == "movement"]
    assert summary["clear_accepted"] is True
    assert summary["accounting"]["hostile_originated_damage"] == 10
    assert "application/json" in render_timeline_html(model)


def test_full_and_delta_union_and_periodic_pet_output_mask_fresh_outage():
    direct1, dot, pet, direct2 = (_event(1, 1000), _event(2, 4000, effect=2, amount=20),
                                  _event(3, 5000, pet=True, amount=30), _event(4, 8000))
    trace = _trace([{"timestamp_ms": 9000, "sequence": 9, "action": "boss_killed",
                     "result": "confirmed_unit_death", "target": {"entry": 41570}}])
    full = _full([pet, direct2])
    full["abilities"] = [_ability(event) for event in (direct1, dot, pet, direct2)]
    rows = [_bound("trace", trace), *[_bound("combat_log", row) for row in _delta_frames([direct1, dot, pet], 0, 3)],
            _bound("combat_log", full)]
    _, summary = build_timeline_from_rows(rows, _report())
    actor = summary["actors"]["7"]
    assert summary["completeness"]["combat_event_count"] == 4
    assert actor["activity"]["longest_fresh_attack_outage_ms"] == 7000
    assert actor["activity"]["outage_masked_periodic_damage"] == 20
    assert actor["activity"]["outage_masked_owned_source_damage"] == 30
    assert actor["damage"]["direct"] == 20
    assert actor["damage"]["periodic"] == 20
    assert actor["damage"]["owned_source"] == 30


def test_report_only_failure_flags_absent_pre_failure_trace_without_inventing_metrics():
    _, summary = build_timeline_from_rows([], _report(failed=True))
    assert summary["clear_accepted"] is False
    assert summary["completeness"]["absent_pre_failure_trace"] is True
    assert summary["accounting"]["exact_party_dps"] is None
    assert summary["actors"] == {}


def test_html_preserves_large_identities_and_escapes_untrusted_event_text():
    model = {"identity": {"server_epoch": 14864252641801830}, "window": {}, "actors": {},
             "events": [{"at_ms": 1, "actor_guid": 1, "kind": "decision",
                         "result": "</script><img src=x onerror=alert(1)>"}], "completeness": {}}
    html = render_timeline_html(model)
    assert '"14864252641801830"' in html
    assert "</script><img" not in html
    assert "full event" in html


def test_hostile_accounting_excludes_incoming_and_owned_friendly_damage():
    hostile = _event(1, 1000, amount=100)
    pet = _event(2, 1100, pet=True, amount=20)
    incoming = {**_event(3, 1200, amount=90, target=0), "source_guid": 39,
                "source_entry": 41570, "target_guid": 7, "source_is_pet": False}
    friendly = {**_event(4, 1300, amount=30, target=417), "target_guid": 70}
    death = _trace([{"timestamp_ms": 2000, "sequence": 1, "action": "boss_killed",
                     "result": "confirmed_unit_death", "target": {"entry": 41570}}])
    rows = [_bound("trace", death), _bound("combat_log", _full([hostile, pet, incoming, friendly]))]
    _, summary = build_timeline_from_rows(rows, _report())
    assert summary["accounting"]["hostile_originated_damage"] == 120
    assert summary["accounting"]["excluded_friendly_damage"] == 30


def test_immutable_context_preserves_stale_target_and_rejected_attempt_provenance():
    context = {**IDENTITY, "actor": {"guid": 7, "role": "dps"},
               "event_target": {"guid": 99, "entry": 41570, "native_present": True},
               "native_actor": {"native_present": True, "moving": False},
               "target_return": {"observed_at_ms": 900, "age_ms": 100, "current_at_record": False,
                                 "stale": True, "observation": {"bind_result": "old_failure"}}}
    attempt = {"recorded_at_ms": 1000, "phase": "cast", "action": {"spell_id": 123,
               "target_guid": 99}, "failure": {"result": "out_of_range", "reason": "range",
               "gates": {"in_range": False}}}
    entries = [{**context, "timestamp_ms": 1000, "sequence": 1,
                "native_selected_target": {"guid": 99}, "combat_attempt": attempt},
               {**context, "timestamp_ms": 1100, "sequence": 2,
                "native_selected_target": {"guid": 0, "native_present": False}}]
    model, _ = build_timeline_from_rows([_bound("trace", _trace(entries))], _report(failed=True))
    decision = next(event for event in model["events"] if event["kind"] == "decision")
    assert decision["observation_quality"]["target_return"] == "stale"
    assert decision["target_return"]["observed_at_ms"] == 900
    assert any(event["kind"] == "native_attempt_rejected" for event in model["events"])
    assert not any(event["kind"] == "native_submission" for event in model["events"])
    rejected = next(event for event in model["events"] if event["kind"] == "native_attempt_rejected")
    assert rejected["action_phase"] == "cast"
    assert "phase" not in rejected
    transition = next(event for event in model["events"] if event["kind"] == "target_transition")
    assert transition["target_guid"] == 0


def test_diagnosis_target_return_uses_own_time_and_deduplicates_cached_exports():
    target_return = {"evaluated": True, "valid": True, "current": False,
                     "observed_at_ms": 900, "attempt_id": 2, "route_generation": 4,
                     "route_node_id": "boss", "head_fact": "head_attackable",
                     "body": {"guid": 99}, "head": {"guid": 100},
                     "bind_result": "bound", "snapshot_revision": 7}
    payload = {"raid_runtime": {**IDENTITY}, "bots": [{"identity": {"bot_guid": 7},
               "diagnosis": {"magmaw_target_return": target_return},
               "snapshot": {"runtime": {"last_decision_tick_ms": 1000},
                            "policy": {"decision_kernel": {"candidates": []}},
                            "movement": {"is_moving": False}}}]}
    model, summary = build_timeline_from_rows(
        [_bound("diagnosis", payload), _bound("diagnosis", payload)], _report(failed=True))
    observed = [event for event in model["events"] if event["kind"] == "target_return_observation"]
    assert len(observed) == 1
    assert observed[0]["at_ms"] == 900
    assert observed[0]["stale_relative_to_export"] is True
    assert summary["phase_intervals"] == [{"actor_guid": 7, "phase": "head_attackable",
                                           "start_ms": 900, "end_ms": 900,
                                           "boundary_provenance": "historical_diagnosis_observed_at",
                                           "start_boundary_provenance": "historical_diagnosis_observed_at",
                                           "end_boundary_provenance": "historical_diagnosis_observed_at",
                                           "conflict": False}]


def test_partial_identity_without_matching_normalized_binding_is_rejected():
    row = _bound("trace", {"cohort_id": "raid", "bots": []})
    row["identity_binding"]["canonical_identity_sha256"] = "b" * 64
    _, summary = build_timeline_from_rows([row], _report())
    assert summary["completeness"]["identity_rejections"][0]["channel"] == "trace"


def test_same_scope_wrong_or_missing_target_cannot_close_native_window():
    report = _report()
    report["development_run"]["accepted_boss_identity"].update(
        route_generation=4, route_node_id="boss")
    trace = _trace([{"timestamp_ms": 2000, "sequence": 1, "action": "boss_killed",
                     "result": "confirmed_unit_death", "route_generation": 4,
                     "route_node_id": "boss", "target": {"entry": 999}},
                    {"timestamp_ms": 3000, "sequence": 2, "action": "boss_killed",
                     "result": "confirmed_unit_death", "route_generation": 4,
                     "route_node_id": "boss"}])
    _, summary = build_timeline_from_rows(
        [_bound("trace", trace), _bound("combat_log", _full([_event(1, 1000)]))], report)
    assert summary["window"]["native_boss_death_at_ms"] is None
    assert summary["accounting"]["exact_party_dps"] is None


def test_legacy_boss_kill_counter_resolves_through_scoped_combat_target():
    report = _report()
    report["development_run"]["accepted_boss_identity"].update(
        route_generation=4, route_node_id="boss")
    legacy = _trace([{"timestamp_ms": 2000, "sequence": 1, "action": "boss_killed",
                      "result": "confirmed_unit_death", "route_generation": 4,
                      "route_node_id": "boss", "target_id": 39}])
    hit = {**_event(1, 1000), "target_guid": 39, "route_node_id": "boss"}
    _, summary = build_timeline_from_rows(
        [_bound("trace", legacy), _bound("combat_log", _full([hit]))], report)
    assert summary["window"]["native_boss_death_at_ms"] == 2000
    assert summary["window"]["elapsed_seconds"] == 1.0


def test_periodic_pet_only_actor_gets_full_window_direct_outage():
    events = [_event(1, 1000, effect=2), _event(2, 5000, effect=2, amount=20),
              _event(3, 6000, pet=True, amount=30)]
    trace = _trace([{"timestamp_ms": 10000, "sequence": 1, "action": "boss_killed",
                     "result": "confirmed_unit_death", "target": {"entry": 41570}}])
    _, summary = build_timeline_from_rows(
        [_bound("trace", trace), _bound("combat_log", _full(events))], _report())
    activity = summary["actors"]["7"]["activity"]
    assert activity["longest_fresh_attack_outage_ms"] == 9000
    assert activity["outage_masked_periodic_damage"] == 20
    assert activity["outage_masked_owned_source_damage"] == 30


def test_cross_actor_phase_disagreement_stays_attributable_and_conflicted():
    def bot(guid, fact):
        return {"identity": {"bot_guid": guid}, "diagnosis": {"magmaw_target_return": {
            "evaluated": True, "valid": True, "current": False, "observed_at_ms": 900,
            "attempt_id": 2, "route_generation": 4, "route_node_id": "boss",
            "head_fact": fact, "bind_result": "bound"}}, "snapshot": {}}
    payload = {"raid_runtime": {**IDENTITY}, "bots": [bot(7, "body"), bot(8, "head")]}
    _, summary = build_timeline_from_rows([_bound("diagnosis", payload)], _report(failed=True))
    assert len(summary["phase_intervals"]) == 2
    assert all(row["conflict"] is True for row in summary["phase_intervals"])


def test_html_shows_legacy_warning_missing_fields_and_phase_conflicts():
    model = {"identity": {}, "window": {}, "actors": {}, "events": [],
             "phase_intervals": [{"actor_guid": 7, "phase": "head", "start_ms": 1,
                                   "end_ms": 2, "conflict": True,
                                   "boundary_provenance": "observed"}],
             "completeness": {"legacy_historical_metadata_warning": "legacy warning",
                              "missing_observations": ["native_target"]}}
    html = render_timeline_html(model)
    assert "legacy warning" in html and "native_target" in html
    assert "Conflicting attributable phase observations" in html


def test_actor_role_comes_from_identity_scoped_admission_receipt():
    report = _report()
    report["accepted_raid_runtime"] = {
        "server_epoch": 11, "attempt_id": 2,
        "admission_receipt": {"server_epoch": 11, "attempt_id": 2,
                              "members": [{"guid": 7, "name": "Mage", "role": "dps",
                                           "class_id": 8, "class_spec": "arcane_mage"}]},
        "roster": [{"guid": 7, "name": "Mage", "role": "healer"}],
    }
    _, summary = build_timeline_from_rows(
        [_bound("combat_log", _full([_event(1, 1000)]))], report)
    actor = summary["actors"]["7"]
    assert actor["role"] == "dps"
    assert actor["role_provenance"] == "accepted_raid_runtime.admission_receipt.members"
