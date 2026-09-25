"""Header-only tests for native route contracts (parse, completion, owner, transport).

The pure headers under test have no server dependencies; they are compiled
with g++ exactly like the other header-only bot tests.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "experiments/configs/validation_scenarios_cata_001.json"
INCLUDES = ["src/server/game", "src/common"]


def _compile_and_run(tmp_path: Path, program: str) -> str:
    source = tmp_path / "program.cpp"
    binary = tmp_path / "program"
    source.write_text(program)
    command = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror"]
    for include in INCLUDES:
        command += ["-I", str(ROOT / include)]
    subprocess.run(command + [str(source), "-o", str(binary)], check=True, cwd=ROOT)
    return subprocess.run(
        [str(binary)], check=True, cwd=ROOT, capture_output=True, text=True
    ).stdout


PRELUDE = r'''
#include "Bots/BotValidationRouteNativeContract.h"
#include "Bots/BotValidationRouteNativeLogic.h"
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

using namespace BotValidationRouteNative;

static int failures = 0;
#define CHECK(condition) do { if (!(condition)) { std::fprintf(stderr, "FAIL %s:%d %s\n", __FILE__, __LINE__, #condition); ++failures; } } while (0)

[[maybe_unused]] static Json ParseObject(char const* text)
{
    Json value;
    ParseError error = ParseObjectText(text, value);
    if (error)
    {
        std::fprintf(stderr, "json error %s for %s\n", error.Detail.c_str(), text);
        ++failures;
    }
    return value;
}

[[maybe_unused]] static ParseError Interaction(char const* text, InteractionContract& out)
{
    return ParseInteraction(ParseObject(text), out);
}

[[maybe_unused]] static ParseError Completion(char const* text, CompletionContract& out)
{
    return ParseCompletion(ParseObject(text), out);
}

[[maybe_unused]] static ParseError Transport(char const* text, TransportContract& out)
{
    return ParseTransport(ParseObject(text), out);
}

struct FakeFacts final : FactSource
{
    std::vector<ActorFact> CreatureFacts;
    std::vector<ActorFact> ObjectFacts;
    std::vector<MemberFact> MemberFacts;
    TransportFact TransportState;
    bool HasBoss = false;
    std::uint32_t Boss = 0;

    std::vector<ActorFact> Creatures(std::uint32_t entry, std::uint64_t spawnId) const override
    {
        std::vector<ActorFact> out;
        for (ActorFact const& fact : CreatureFacts)
            if ((!entry || fact.Entry == entry) && (!spawnId || fact.SpawnId == spawnId))
                out.push_back(fact);
        return out;
    }
    bool AbsenceAuthoritative = true;
    ObjectQuery GameObjects(std::uint32_t entry, std::uint64_t spawnId) const override
    {
        ObjectQuery out;
        for (ActorFact const& fact : ObjectFacts)
            if ((!entry || fact.Entry == entry) && (!spawnId || fact.SpawnId == spawnId))
                out.Facts.push_back(fact);
        out.AbsenceAuthoritative = AbsenceAuthoritative && spawnId;
        return out;
    }
    bool BossState(std::uint32_t index, std::uint32_t& state) const override
    {
        if (!HasBoss || index != 5)
            return false;
        state = Boss;
        return true;
    }
    std::vector<MemberFact> Members() const override { return MemberFacts; }
    TransportFact Transport(std::uint32_t, std::uint64_t) const override { return TransportState; }
};
'''


def test_bwd_contract_shapes_parse_with_required_bounds(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PRELUDE + r'''
int main()
{
    InteractionContract bell;
    // Every declared interaction must be bounded in time.
    CHECK(Interaction(R"({"action": "gameobject_use", "entry": 204276})", bell).Detail == "timeout_required");
    CHECK(!Interaction(R"({"action": "gameobject_use", "entry": 204276, "spawn_id": 235153, "owner_role": "dps", "max_attempts": 3, "retry_interval_ms": 3000, "timeout_ms": 60000, "gather": true, "gather_radius_yards": 12.0})", bell));
    CHECK(bell.Declared && bell.Action == InteractionAction::GameObjectUse);
    CHECK(bell.Target == TargetType::GameObject && bell.Entry == 204276 && bell.SpawnId == 235153);
    CHECK(bell.TimeoutMs == 60000 && bell.MaxAttempts == 3 && bell.Gather);

    InteractionContract finkle;
    CHECK(!Interaction(R"({"action": "gossip_select_sequence", "entry": 44202, "menus": [11812, 11834, 11835, 11836, 11837], "option": 0, "max_attempts": 3, "retry_interval_ms": 1000, "timeout_ms": 90000})", finkle));
    CHECK(finkle.Menus.size() == 5 && finkle.Menus.front() == 11812 && finkle.Target == TargetType::Any);

    InteractionContract orb;
    CHECK(!Interaction(R"({"action": "gossip_select", "entry": 203254, "menu": 11492, "option": 0, "max_attempts": 3, "retry_interval_ms": 1000, "timeout_ms": 60000})", orb));
    CHECK(orb.Menus.size() == 1 && orb.Menus.front() == 11492 && orb.Option == 0);

    for (char const* text : {
        R"({"kind": "gameobject_selectable", "entry": 204276})",
        R"({"kind": "boss_summoned", "entry": 41442})",
        R"({"kind": "creature_summoned", "entry": 41376})",
        R"({"kind": "aura_present", "entry": 44418, "spell_id": 82705})",
        R"({"kind": "creature_aggressive_with_victim", "entry": 43296})",
        R"({"kind": "creature_grounded_aggressive_or_engaged", "entry": 41442, "timeout_ms": 120000})" })
    {
        CompletionContract completion;
        CHECK(!Completion(text, completion));
        CHECK(completion.Declared);
    }
    CompletionContract bounded;
    CHECK(!Completion(R"({"kind": "all_of", "contracts": [{"kind": "creature_summoned", "entry": 41376}], "timeout_ms": 120000})", bounded));
    CHECK(bounded.TimeoutMs == 120000 && bounded.Children.front().TimeoutMs == 0);
    return failures ? 1 : 0;
}
''')


def test_interaction_only_nodes_never_complete(tmp_path: Path) -> None:
    """MAJOR 1: an interaction proves nothing without an observed completion."""

    _compile_and_run(tmp_path, PRELUDE + r'''
int main()
{
    InteractionContract interaction;
    CompletionContract none;
    TransportContract noTransport;
    CHECK(!Interaction(R"({"action": "gameobject_use", "entry": 1, "max_attempts": 3, "retry_interval_ms": 1000, "timeout_ms": 1000})", interaction));
    CHECK(ValidateNodeShape("interaction", interaction, none, noTransport).Detail
        == "interaction_requires_completion");
    CompletionContract completion;
    CHECK(!Completion(R"({"kind": "creature_summoned", "entry": 2})", completion));
    CHECK(!ValidateNodeShape("interaction", interaction, completion, noTransport));
    return failures ? 1 : 0;
}
''')


def test_unevaluated_and_unknown_contracts_fail_closed(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PRELUDE + r'''
static bool Invalid(ParseError const& error, std::string const& detail)
{
    return error.Kind == ParseError::Code::Invalid && error.Detail.rfind(detail, 0) == 0;
}

int main()
{
    CompletionContract completion;
    // Formerly accepted but never evaluated: now rejected at parse time.
    CHECK(Invalid(Completion(R"({"kind": "intro_complete_and_elevator_ready", "entry": 41376})", completion), "kind_unknown:intro_complete_and_elevator_ready"));
    CHECK(Invalid(Completion(R"({"kind": "player_in_nefarian_arena"})", completion), "kind_unknown:player_in_nefarian_arena"));
    CHECK(Invalid(Completion(R"({"kind": "boss_summoned"})", completion), "entry_missing"));
    CHECK(Invalid(Completion(R"({"kind": "boss_summoned", "entry": 1, "spell_id": 2})", completion), "field_unexpected:spell_id"));
    CHECK(Completion(R"({"kind": "boss_summoned", "entry": 1, "bogus": 2})", completion).Kind == ParseError::Code::UnknownField);
    CHECK(Invalid(Completion(R"({"kind": "instance_boss_state", "boss_index": 5, "boss_state": "dead"})", completion), "boss_state_shape"));
    CHECK(Invalid(Completion(R"({"kind": "any_of", "contracts": []})", completion), "composite_shape"));
    CHECK(Invalid(Completion(R"({"kind": "any_of", "contracts": [{"kind": "player_in_nefarian_arena"}]})", completion), "child:kind_unknown"));
    CHECK(Invalid(Completion(R"({"kind": "on_transport", "transport_entry": 1, "scope": "some"})", completion), "scope_unknown"));
    // Absence is only authoritative in the route instance's spawn-id store.
    CHECK(Invalid(Completion(R"({"kind": "gameobject_despawned", "entry": 203254})", completion), "despawn_requires_spawn_id"));
    CHECK(Invalid(Completion(R"({"kind": "any_of", "contracts": [{"kind": "creature_summoned", "entry": 1, "timeout_ms": 5}]})", completion), "child:timeout_only_top_level"));
    CHECK(Invalid(Completion(R"({"kind": "creature_summoned", "entry": 1, "timeout_ms": 0})", completion), "timeout_invalid"));

    InteractionContract interaction;
    CHECK(Interaction(R"({"action": "gameobject_use", "entry": 1, "menu": 2})", interaction).Kind == ParseError::Code::Invalid);
    CHECK(Interaction(R"({"action": "teleport", "entry": 1})", interaction).Detail == "action_unknown");
    CHECK(Interaction(R"({"action": "gameobject_use"})", interaction).Detail == "target_missing");
    CHECK(Interaction(R"({"action": "gameobject_use", "entry": 1, "whisper": 1})", interaction).Kind == ParseError::Code::UnknownField);
    CHECK(Interaction(R"({"action": "gossip_select", "entry": 1})", interaction).Detail == "gossip_menu_missing");
    CHECK(Interaction(R"({"action": "gossip_select", "entry": 1, "menu": 3, "menus": [4]})", interaction).Detail == "gossip_menu_ambiguous");
    CHECK(Interaction(R"({"action": "spellclick", "entry": 1, "seat": 0})", interaction).Detail == "seat_unexpected");
    CHECK(Interaction(R"({"action": "vehicle_enter", "entry": 1, "seat": 9})", interaction).Detail == "field_type_or_range");
    CHECK(Interaction(R"({"action": "spellclick", "entry": 1, "target_type": "gameobject"})", interaction).Detail == "target_type_conflicts_with_action");
    CHECK(Interaction(R"({"action": "area_trigger", "area_trigger_id": 7, "entry": 1})", interaction).Detail == "area_trigger_shape");
    CHECK(Interaction(R"({"action": "gameobject_use", "entry": 1, "owner_role": "pet"})", interaction).Detail == "owner_role_unknown");
    CHECK(Interaction(R"({"action": "gameobject_use", "entry": 1, "owner_role": "dps", "owner_roster_slot": 3})", interaction).Detail == "owner_ambiguous");
    CHECK(Interaction(R"({"action": "gameobject_use", "entry": 1, "backup_roster_slot": 3})", interaction).Detail == "backup_without_owner");
    CHECK(Interaction(R"({"action": "gameobject_use", "entry": 1, "owner_roster_slot": 3, "backup_roster_slot": 3})", interaction).Detail == "backup_equals_owner");
    CHECK(Interaction(R"({"action": "gameobject_use", "entry": 1, "gather": true, "timeout_ms": 1})", interaction).Detail == "gather_radius_invalid");
    // Gameobjects use the native reach rule; creature ranges only tighten 5 yd.
    CHECK(Interaction(R"({"action": "gameobject_use", "entry": 1, "range_yards": 3.0, "timeout_ms": 1})", interaction).Detail == "range_not_supported_for_target");
    CHECK(Interaction(R"({"action": "spellclick", "entry": 1, "range_yards": 6.0, "timeout_ms": 1})", interaction).Detail == "range_invalid");
    CHECK(!Interaction(R"({"action": "spellclick", "entry": 1, "range_yards": 4.0, "max_attempts": 3, "retry_interval_ms": 1000, "timeout_ms": 1})", interaction));
    // Every interaction commits native requests: attempts are bounded and
    // each one (including the last) gets a settle window.
    CHECK(Interaction(R"({"action": "spellclick", "entry": 1, "timeout_ms": 1})", interaction).Detail == "max_attempts_required");
    CHECK(Interaction(R"({"action": "spellclick", "entry": 1, "max_attempts": 2, "timeout_ms": 1})", interaction).Detail == "retry_interval_required");
    CHECK(Interaction(R"({"action": "spellclick", "entry": 1, "max_attempts": 2, "retry_interval_ms": 10, "timeout_ms": 1})", interaction).Detail == "retry_interval_required");

    TransportContract transport;
    CHECK(Transport(R"({"entry": 1, "board_point": [1, 2, 3]})", transport).Detail == "board_readiness_ambiguous");
    CHECK(Transport(R"({"entry": 1, "board_stop_frame": 0, "board_transport_z": 1, "board_point": [1, 2, 3]})", transport).Detail == "board_readiness_ambiguous");
    CHECK(Transport(R"({"entry": 1, "board_stop_frame": 0})", transport).Detail == "board_point_missing");
    CHECK(Transport(R"({"entry": 1, "board_stop_frame": 0, "board_point": [1, 2]})", transport).Detail == "field_type_or_range");
    CHECK(Transport(R"({"entry": 1, "board_stop_frame": 0, "board_point": [1, 2, 3], "exit_stop_frame": 1})", transport).Detail == "exit_shape");
    CHECK(Transport(R"({"entry": 1, "board_stop_frame": 0, "board_point": [1, 2, 3], "disembark_point": [1, 2, 3]})", transport).Detail == "exit_shape");
    CHECK(Transport(R"({"entry": 1, "board_stop_frame": 0, "board_point": [1, 2, 3]})", transport).Detail == "timeout_required");
    CHECK(Transport(R"({"entry": 1, "board_stop_frame": 0, "board_point": [1, 2, 3], "timeout_ms": 1, "max_submissions": 0})", transport).Detail == "max_submissions_invalid");
    CHECK(Transport(R"({"entry": 1, "board_stop_frame": 0, "board_point": [1, 2, 3], "timeout_ms": 1, "floor_tolerance_yards": 3.0})", transport).Detail == "tolerance_invalid");
    // Floor tolerance stays well below the 1.6 yd navmesh step height.
    CHECK(Transport(R"({"entry": 1, "board_stop_frame": 0, "board_point": [1, 2, 3], "timeout_ms": 1, "floor_tolerance_yards": 1.5})", transport).Detail == "tolerance_invalid");
    CHECK(Transport(R"({"entry": 1, "board_stop_frame": 0, "board_point": [1, 2, 3], "timeout_ms": 1, "footprint_margin_yards": 0.5})", transport).Kind == ParseError::Code::UnknownField);

    InteractionContract none;
    CompletionContract noCompletion;
    TransportContract noTransport;
    CHECK(ValidateNodeShape("transport", none, noCompletion, noTransport).Detail == "transport_kind_requires_transport_contract");
    CHECK(!Transport(R"({"entry": 1, "board_stop_frame": 0, "board_point": [1, 2, 3], "timeout_ms": 1})", transport));
    CHECK(ValidateNodeShape("descent", none, noCompletion, transport).Detail == "transport_contract_requires_transport_kind");
    CHECK(ValidateNodeShape("interaction", none, noCompletion, noTransport).Detail == "interaction_kind_requires_contract");
    CHECK(!Interaction(R"({"action": "gameobject_use", "entry": 1, "max_attempts": 3, "retry_interval_ms": 1000, "timeout_ms": 1})", interaction));
    CHECK(ValidateNodeShape("boss", interaction, noCompletion, noTransport).Detail == "interaction_contract_requires_interaction_kind");
    CHECK(!Completion(R"({"kind": "vehicle_seated", "vehicle_entry": 1, "scope": "owner"})", completion));
    CHECK(ValidateNodeShape("interaction", none, completion, noTransport).Detail == "owner_scope_requires_interaction");
    // Ordinary route rows declare nothing and stay valid.
    CHECK(!ValidateNodeShape("trash", none, noCompletion, noTransport));
    CHECK(!ValidateNodeShape("boss", none, noCompletion, noTransport));
    return failures ? 1 : 0;
}
''')


def test_generic_interaction_fields_owner_election_and_bounded_attempts(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PRELUDE + r'''
int main()
{
    std::vector<MemberView> members = {
        { 40, true, "tank", 1 },
        { 20, true, "dps", 6 },
        { 30, true, "dps", 7 },
        { 10, true, "healer", 3 },
    };
    InteractionContract legacy;
    CHECK(!Interaction(R"({"action": "gameobject_use", "entry": 1, "max_attempts": 3, "retry_interval_ms": 1000, "timeout_ms": 1})", legacy));
    // Historical default: the lowest living GUID owns the interaction.
    CHECK(ElectOwner(legacy, members).Owner == 10);

    InteractionContract byRole;
    CHECK(!Interaction(R"({"action": "gameobject_use", "entry": 1, "owner_role": "dps", "max_attempts": 3, "retry_interval_ms": 1000, "timeout_ms": 1})", byRole));
    CHECK(ElectOwner(byRole, members).Owner == 20);
    members[1].Alive = false;
    CHECK(ElectOwner(byRole, members).Owner == 30);

    InteractionContract bySlot;
    CHECK(!Interaction(R"({"action": "spellclick", "entry": 5, "owner_roster_slot": 6, "backup_roster_slot": 1, "max_attempts": 3, "retry_interval_ms": 1000, "timeout_ms": 1})", bySlot));
    OwnerElection election = ElectOwner(bySlot, members);
    CHECK(election.Owner == 40 && election.UsedBackup && election.Reason == "backup_roster_slot");
    members[1].Alive = true;
    election = ElectOwner(bySlot, members);
    CHECK(election.Owner == 20 && !election.UsedBackup);
    members[0].Alive = false;
    members[1].Alive = false;
    CHECK(ElectOwner(bySlot, members).Reason == "interaction_owner_unavailable");

    InteractionContract bounded;
    CHECK(!Interaction(R"({"action": "vehicle_enter", "entry": 5, "seat": 2, "max_attempts": 2, "retry_interval_ms": 1000, "timeout_ms": 5000, "gather": true, "gather_radius_yards": 8.0, "range_yards": 4.5})", bounded));
    CHECK(bounded.Seat == 2 && bounded.Gather && bounded.GatherRadiusYards == 8.0f && bounded.RangeYards == 4.5f);
    AttemptState attempts;
    CHECK(EvaluateAttemptGate(bounded, attempts, 1000, 1000) == AttemptGate::Allowed);
    RecordAttempt(attempts, 1000);
    CHECK(EvaluateAttemptGate(bounded, attempts, 1000, 1500) == AttemptGate::RetryWait);
    CHECK(EvaluateAttemptGate(bounded, attempts, 1000, 2000) == AttemptGate::Allowed);
    RecordAttempt(attempts, 2000);
    // The last attempt keeps its full retry interval before exhaustion fails.
    CHECK(EvaluateAttemptGate(bounded, attempts, 1000, 2500) == AttemptGate::RetryWait);
    CHECK(EvaluateAttemptGate(bounded, attempts, 1000, 3000) == AttemptGate::AttemptsExhausted);
    CHECK(EvaluateAttemptGate(bounded, attempts, 1000, 6000) == AttemptGate::TimedOut);

    InteractionObservation observation;
    CHECK(DecideInteraction(bounded, observation, AttemptGate::Allowed).Reason == "native_interaction_target_missing");
    observation.TargetResolved = true;
    observation.TargetAmbiguous = true;
    CHECK(DecideInteraction(bounded, observation, AttemptGate::Allowed).Reason == "native_interaction_target_ambiguous");
    observation.TargetAmbiguous = false;
    CHECK(DecideInteraction(bounded, observation, AttemptGate::Allowed).Step == InteractionStep::Approach);
    observation.InRange = true;
    InteractionDecision decision = DecideInteraction(bounded, observation, AttemptGate::Allowed);
    CHECK(decision.Step == InteractionStep::VehicleEnter && decision.CountsAsAttempt);
    CHECK(DecideInteraction(bounded, observation, AttemptGate::RetryWait).Step == InteractionStep::Hold);
    decision = DecideInteraction(bounded, observation, AttemptGate::TimedOut);
    CHECK(decision.Step == InteractionStep::Fail && decision.Reason == "native_interaction_timeout");
    decision = DecideInteraction(bounded, observation, AttemptGate::AttemptsExhausted);
    CHECK(decision.Step == InteractionStep::Fail && decision.Reason == "native_interaction_attempts_exhausted");

    InteractionContract gossip;
    CHECK(!Interaction(R"({"action": "gossip_select_sequence", "entry": 44202, "menus": [11812, 11834], "option": 0, "max_attempts": 1, "retry_interval_ms": 1000, "timeout_ms": 1000})", gossip));
    CHECK(DecideInteraction(gossip, observation, AttemptGate::Allowed).Step == InteractionStep::GossipOpen);
    observation.GossipBoundToTarget = true;
    observation.CurrentGossipMenu = 11834;
    decision = DecideInteraction(gossip, observation, AttemptGate::AttemptsExhausted);
    // Continuing the dialogue the last attempt opened is not a new attempt.
    CHECK(decision.Step == InteractionStep::GossipSelect && !decision.CountsAsAttempt);
    observation.CurrentGossipMenu = 99999;
    CHECK(DecideInteraction(gossip, observation, AttemptGate::AttemptsExhausted).Step == InteractionStep::Fail);
    CHECK(DecideInteraction(gossip, observation, AttemptGate::RetryWait).Step == InteractionStep::Hold);

    InteractionContract trigger;
    CHECK(!Interaction(R"({"action": "area_trigger", "area_trigger_id": 6581, "max_attempts": 3, "retry_interval_ms": 1000, "timeout_ms": 1})", trigger));
    InteractionObservation outside;
    // An unresolved trigger never produces a move (no walk toward 0,0,0).
    decision = DecideInteraction(trigger, outside, AttemptGate::Allowed);
    CHECK(decision.Step == InteractionStep::Hold && decision.Reason == "native_interaction_area_trigger_invalid");
    outside.TargetResolved = true;
    CHECK(DecideInteraction(trigger, outside, AttemptGate::Allowed).Step == InteractionStep::Approach);
    outside.InRange = true;
    CHECK(DecideInteraction(trigger, outside, AttemptGate::Allowed).Step == InteractionStep::AreaTrigger);
    return failures ? 1 : 0;
}
''')


def test_every_completion_kind_is_evaluated(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PRELUDE + r'''
int main()
{
    FakeFacts facts;
    CompletionMemory memory;
    CompletionContract contract;

    CHECK(!Completion(R"({"kind": "gameobject_selectable", "entry": 204276})", contract));
    ActorFact bell; bell.Entry = 204276; bell.Spawned = true; bell.Alive = true;
    facts.ObjectFacts = { bell };
    CHECK(!EvaluateCompletion(contract, facts, memory).Satisfied);
    facts.ObjectFacts[0].Selectable = facts.ObjectFacts[0].Interactable = true;
    CHECK(EvaluateCompletion(contract, facts, memory).Satisfied);

    // Despawn only after the object was observed spawned in this scope, and
    // only when absence is proven by the route instance's spawn-id store.
    CHECK(!Completion(R"({"kind": "gameobject_despawned", "entry": 203254, "spawn_id": 239510})", contract));
    facts.ObjectFacts.clear();
    CHECK(EvaluateCompletion(contract, facts, memory).Reason == "gameobject_never_observed_spawned");
    ActorFact orb; orb.Entry = 203254; orb.SpawnId = 239510; orb.Spawned = true;
    facts.ObjectFacts = { orb };
    CHECK(!EvaluateCompletion(contract, facts, memory).Satisfied);
    // An evaluator that cannot prove absence (grid unloaded, wrong map)
    // sees "unknown", never "despawned".
    facts.ObjectFacts.clear();
    facts.AbsenceAuthoritative = false;
    CHECK(EvaluateCompletion(contract, facts, memory).Reason == "gameobject_absence_unknown");
    facts.AbsenceAuthoritative = true;
    CHECK(EvaluateCompletion(contract, facts, memory).Satisfied);
    facts.ObjectFacts = { orb };
    facts.ObjectFacts[0].Spawned = false;
    facts.AbsenceAuthoritative = false;
    // Present but unspawned (respawn timer) is known despawned.
    CHECK(EvaluateCompletion(contract, facts, memory).Satisfied);
    facts.AbsenceAuthoritative = true;

    ActorFact nefarian; nefarian.Entry = 41376; nefarian.Alive = true; nefarian.Flying = true;
    CHECK(!Completion(R"({"kind": "creature_summoned", "entry": 41376})", contract));
    CHECK(!EvaluateCompletion(contract, facts, memory).Satisfied);
    facts.CreatureFacts = { nefarian };
    CHECK(EvaluateCompletion(contract, facts, memory).Satisfied);
    CHECK(!Completion(R"({"kind": "boss_summoned", "entry": 41376})", contract));
    CHECK(EvaluateCompletion(contract, facts, memory).Satisfied);
    CHECK(!Completion(R"({"kind": "creature_grounded_aggressive_or_engaged", "entry": 41376})", contract));
    facts.CreatureFacts[0].InCombat = true;
    CHECK(!EvaluateCompletion(contract, facts, memory).Satisfied);
    facts.CreatureFacts[0].Flying = false;
    CHECK(EvaluateCompletion(contract, facts, memory).Satisfied);
    CHECK(!Completion(R"({"kind": "creature_aggressive_with_victim", "entry": 41376})", contract));
    facts.CreatureFacts[0].ReactAggressive = true;
    CHECK(!EvaluateCompletion(contract, facts, memory).Satisfied);
    facts.CreatureFacts[0].HasVictim = true;
    CHECK(EvaluateCompletion(contract, facts, memory).Satisfied);
    CHECK(!Completion(R"({"kind": "aura_present", "entry": 41376, "spell_id": 82705})", contract));
    CHECK(!EvaluateCompletion(contract, facts, memory).Satisfied);
    facts.CreatureFacts[0].AuraIds = { 82705 };
    CHECK(EvaluateCompletion(contract, facts, memory).Satisfied);

    CHECK(!Completion(R"({"kind": "instance_boss_state", "boss_index": 5, "boss_state": "done"})", contract));
    CHECK(EvaluateCompletion(contract, facts, memory).Reason == "instance_script_unavailable");
    facts.HasBoss = true;
    facts.Boss = 1;
    CHECK(!EvaluateCompletion(contract, facts, memory).Satisfied);
    facts.Boss = 3;
    CHECK(EvaluateCompletion(contract, facts, memory).Satisfied);

    facts.TransportState.Present = true;
    facts.TransportState.Entry = 207834;
    facts.TransportState.GoState = 24;
    CHECK(!Completion(R"({"kind": "transport_at_stop", "transport_entry": 207834, "stop_frame": 0})", contract));
    CHECK(!EvaluateCompletion(contract, facts, memory).Satisfied);
    facts.TransportState.GoState = 25;
    CHECK(!EvaluateCompletion(contract, facts, memory).Satisfied);
    facts.TransportState.ArrivedAtStop = true;
    CHECK(EvaluateCompletion(contract, facts, memory).Satisfied);

    MemberFact a; a.Guid = 1; a.Alive = true; a.OnRouteInstance = true;
    MemberFact b; b.Guid = 2; b.Alive = true; b.Owner = true; b.OnRouteInstance = true;
    MemberFact dead; dead.Guid = 3;
    facts.MemberFacts = { a, b, dead };
    CHECK(!Completion(R"({"kind": "on_transport", "transport_entry": 207834})", contract));
    CHECK(!EvaluateCompletion(contract, facts, memory).Satisfied);
    facts.MemberFacts[0].OnTransport = true; facts.MemberFacts[0].TransportEntry = 207834;
    CHECK(EvaluateCompletion(contract, facts, memory).Reason == "members_pending:1/2");
    facts.MemberFacts[1].OnTransport = true; facts.MemberFacts[1].TransportEntry = 207834;
    CHECK(EvaluateCompletion(contract, facts, memory).Satisfied);
    // A living member elsewhere (corpse run, other map) blocks "all".
    MemberFact away; away.Guid = 4; away.Alive = true;
    facts.MemberFacts.push_back(away);
    CHECK(EvaluateCompletion(contract, facts, memory).Reason == "members_off_route_map");
    CHECK(!Completion(R"({"kind": "on_transport", "transport_entry": 207834, "scope": "any"})", contract));
    CHECK(EvaluateCompletion(contract, facts, memory).Satisfied);
    facts.MemberFacts.pop_back();
    CHECK(!Completion(R"({"kind": "on_transport", "transport_entry": 207834})", contract));
    facts.TransportState.Ambiguous = true;
    CHECK(EvaluateCompletion(contract, facts, memory).Reason == "transport_ambiguous");
    facts.TransportState.Ambiguous = false;

    CHECK(!Completion(R"({"kind": "vehicle_seated", "vehicle_entry": 900, "seat": 1, "scope": "owner"})", contract));
    CHECK(!EvaluateCompletion(contract, facts, memory).Satisfied);
    facts.MemberFacts[1].VehicleEntry = 900; facts.MemberFacts[1].Seat = 0;
    CHECK(!EvaluateCompletion(contract, facts, memory).Satisfied);
    facts.MemberFacts[1].Seat = 1;
    CHECK(EvaluateCompletion(contract, facts, memory).Satisfied);
    CHECK(!Completion(R"({"kind": "vehicle_seated", "vehicle_entry": 900, "scope": "any"})", contract));
    CHECK(EvaluateCompletion(contract, facts, memory).Satisfied);

    // Composite: the orb needs its despawn and Nefarian's native summon; the
    // despawn alone happens even when Nefarius cannot start the intro.
    FakeFacts orbFacts;
    CompletionMemory orbMemory;
    CHECK(!Completion(R"({"kind": "all_of", "contracts": [{"kind": "gameobject_despawned", "entry": 203254, "spawn_id": 239510}, {"kind": "creature_summoned", "entry": 41376}]})", contract));
    orbFacts.ObjectFacts = { orb };
    orbFacts.ObjectFacts[0].Spawned = true;
    CHECK(!EvaluateCompletion(contract, orbFacts, orbMemory).Satisfied);
    orbFacts.ObjectFacts.clear();
    CHECK(!EvaluateCompletion(contract, orbFacts, orbMemory).Satisfied);
    orbFacts.CreatureFacts = { nefarian };
    CHECK(EvaluateCompletion(contract, orbFacts, orbMemory).Satisfied);
    CHECK(!Completion(R"({"kind": "any_of", "contracts": [{"kind": "gameobject_despawned", "entry": 203254, "spawn_id": 239510}, {"kind": "creature_summoned", "entry": 41376}]})", contract));
    orbFacts.CreatureFacts.clear();
    CHECK(EvaluateCompletion(contract, orbFacts, orbMemory).Satisfied);
    CHECK(!Completion(R"({"kind": "all_of", "contracts": [{"kind": "transport_at_stop", "transport_entry": 207834, "stop_frame": 0}, {"kind": "creature_summoned", "entry": 41376}]})", contract));
    CHECK(!EvaluateCompletion(contract, orbFacts, orbMemory).Satisfied);
    return failures ? 1 : 0;
}
''')


def test_transport_boarding_phases_floors_and_rest_window(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PRELUDE + r'''
static TransportTimeline LowerWingElevator()
{
    // TransportAnimation.dbc rows for GO 203716 (TotalTime 17367 ms).
    TransportTimeline timeline;
    timeline.PeriodMs = 17367;
    timeline.ZKeys = { { 0, 0.0f }, { 1733, 0.0f }, { 1800, -0.072564f }, { 1833, -0.072564f },
        { 8567, -112.67043f }, { 8633, -112.57608f }, { 8667, -112.67043f }, { 10400, -112.67043f },
        { 10467, -112.59728f }, { 10533, -112.67043f }, { 17267, 0.0f }, { 17300, -0.048267f },
        { 17367, 0.0f } };
    return timeline;
}

int main()
{
    // Local frame: a transport facing pi maps world +x to local -x.
    TransportFact arena; arena.Present = true; arena.PositionX = -107.213f; arena.PositionY = -224.62f;
    arena.PositionZ = 7.03378f; arena.Orientation = 3.14159265f;
    Point3 const arenaLocal = LocalOffset(-132.2132f, -224.6203f, 6.5714f, arena);
    CHECK(std::fabs(arenaLocal.X - 25.0f) < 0.01f && std::fabs(arenaLocal.Y) < 0.01f);
    CHECK(InsideBox(arenaLocal, { -71.31f, -71.31f, -8.69f, 71.3f, 71.31f, 9.95f, true }, 0.0f));

    // Rest window: arrival at the top leaves ~2 s; mid-descent leaves none.
    TransportTimeline const timeline = LowerWingElevator();
    std::uint64_t const atArrival = RestRemainingMs(timeline, 17267, 0.0f, 0.75f);
    CHECK(atArrival >= 1900 && atArrival <= 2050);
    CHECK(RestRemainingMs(timeline, 1000, 0.0f, 0.75f) <= 900);
    CHECK(RestRemainingMs(timeline, 5000, 0.0f, 0.75f) == 0);
    CHECK(RestRemainingMs(timeline, 9500, -112.67043f, 0.75f) >= 900);

    TransportContract ride;
    CHECK(!Transport(R"({"entry": 203716, "spawn_id": 235178, "board_transport_z": 186.551, "exit_transport_z": 73.8806, "level_tolerance_yards": 0.75, "wait_point": [-256.35, -224.605, 190.163], "board_point": [-247.349, -224.605, 190.031], "disembark_point": [-241.349, -224.605, 77.361], "exit_point": [-224.0, -224.605, 76.8211], "floor_tolerance_yards": 0.5, "timeout_ms": 240000})", ride));
    CHECK(ride.HasExit() && ride.DisembarkPoint.Valid && ride.MaxSubmissions == 5);
    TransportFact top; top.Present = true; top.Entry = 203716; top.PositionZ = 186.551f;
    CHECK(TransportReadyToBoard(ride, top) && !TransportAtExit(ride, top));
    TransportFact bottom = top; bottom.PositionZ = 73.9f;
    CHECK(!TransportReadyToBoard(ride, bottom) && TransportAtExit(ride, bottom));

    TransportMemberState state;
    TransportMemberObservation o;
    o.Alive = true; o.TransportPresent = true; o.StaticFloorUnderfoot = true;
    o.DistanceToWait = 20.0f; o.DistanceToBoard = 25.0f; o.DistanceToExit = 120.0f;
    CHECK(DecideTransportStep(ride, o, state).Step == TransportStep::MoveToWait);
    o.DistanceToWait = 0.5f; o.DistanceToBoard = 9.0f;
    CHECK(DecideTransportStep(ride, o, state).Step == TransportStep::Hold);
    // Ready, but the remaining rest cannot cover the walk: hold.
    o.ReadyToBoard = true; o.RestRemainingMs = 900; o.TravelToBoardMs = 1300;
    CHECK(DecideTransportStep(ride, o, state).Reason == "transport_rest_window_too_short");
    o.RestRemainingMs = 1973;
    CHECK(DecideTransportStep(ride, o, state).Step == TransportStep::MoveToBoard);
    // At the board point on static ground inside the model box: never board.
    o.DistanceToBoard = 0.4f;
    CHECK(DecideTransportStep(ride, o, state).Reason == "transport_board_point_not_on_platform_floor");
    // On the platform's own surface, still over a closer static floor: no.
    o.TransportFloorUnderfoot = true;
    CHECK(DecideTransportStep(ride, o, state).Step == TransportStep::Blocked);
    // On the platform's own surface, still walking: stop there, then board.
    o.StaticFloorUnderfoot = false; o.Moving = true;
    CHECK(DecideTransportStep(ride, o, state).Step == TransportStep::Stop);
    CHECK(state.PlatformFloorSeen);
    o.Moving = false;
    CHECK(DecideTransportStep(ride, o, state).Step == TransportStep::Board);
    // The platform left while the member stood on it: confirmed, then fail.
    o.ReadyToBoard = false; o.TransportFloorUnderfoot = false;
    o.NowMs = 10000;
    CHECK(DecideTransportStep(ride, o, state).Reason == "transport_member_floor_lost_confirming");
    o.NowMs = 10250;
    CHECK(DecideTransportStep(ride, o, state).Reason == "transport_member_floor_lost_confirming");
    o.NowMs = 10500;
    TransportDecision stranded = DecideTransportStep(ride, o, state);
    CHECK(stranded.Step == TransportStep::Fail && stranded.Reason == "transport_member_stranded_without_floor");
    o.ReadyToBoard = true; o.TransportFloorUnderfoot = true;
    o.OnThisTransport = true;
    CHECK(DecideTransportStep(ride, o, state).Step == TransportStep::HoldAboard);
    CHECK(state.Boarded);
    o.AtExit = true;
    o.DistanceToDisembark = 9.0f;
    CHECK(DecideTransportStep(ride, o, state).Step == TransportStep::MoveToDisembark);
    o.StaticFloorUnderfoot = true;
    CHECK(DecideTransportStep(ride, o, state).Step == TransportStep::Leave);
    o.OnThisTransport = false; o.TransportFloorUnderfoot = false;
    CHECK(DecideTransportStep(ride, o, state).Step == TransportStep::MoveToExit);
    o.DistanceToExit = 1.0f;
    CHECK(DecideTransportStep(ride, o, state).Step == TransportStep::Done);
    CHECK(MemberTransportDone(ride, false, true, 1.0f));
    CHECK(!MemberTransportDone(ride, true, true, 1.0f));
    // Repeated rejected submissions are bounded.
    state.FailedSubmissions = ride.MaxSubmissions;
    CHECK(DecideTransportStep(ride, o, state).Reason == "transport_submissions_exhausted");

    TransportContract board;
    CHECK(!Transport(R"({"entry": 207834, "board_stop_frame": 0, "wait_point": [-158.4, -223.467, 41.3544], "board_point": [-132.2132, -224.6203, 6.5714], "arrival_tolerance_yards": 3.0, "timeout_ms": 180000})", board));
    TransportMemberState boardState;
    TransportMemberObservation b;
    b.Alive = true; b.TransportPresent = true; b.OnThisTransport = true;
    CHECK(DecideTransportStep(board, b, boardState).Step == TransportStep::Done);
    CHECK(MemberTransportDone(board, true, true, 0.0f));
    b.OnThisTransport = false; b.TransportAmbiguous = true;
    CHECK(DecideTransportStep(board, b, boardState).Reason == "transport_ambiguous");
    b.TransportAmbiguous = false; b.OnOtherTransportOrVehicle = true;
    CHECK(DecideTransportStep(board, b, boardState).Reason == "transport_member_on_other_transport");
    // Script-held stop frames have an unbounded rest window.
    b.OnOtherTransportOrVehicle = false; b.StaticFloorUnderfoot = true; b.ReadyToBoard = true;
    b.RestRemainingMs = UnboundedRestMs; b.TravelToBoardMs = 60000; b.DistanceToBoard = 40.0f;
    CHECK(DecideTransportStep(board, b, boardState).Step == TransportStep::MoveToBoard);
    return failures ? 1 : 0;
}
''')


def test_runtime_scope_and_observed_entries(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PRELUDE + r'''
int main()
{
    NodeRuntime runtime;
    runtime.Enter({ 1, 0, 3 }, 1000);
    RecordAttempt(runtime.Attempt, 1000);
    runtime.Enter({ 1, 0, 3 }, 2000);
    CHECK(runtime.Attempt.Attempts == 1 && runtime.StartedAtMs == 1000);
    // A wipe (new wipe generation) is a new scope: attempts and timers reset.
    runtime.VerdictValid = true; runtime.VerdictSatisfied = true;
    runtime.Enter({ 1, 1, 3 }, 5000);
    CHECK(runtime.Attempt.Attempts == 0 && runtime.StartedAtMs == 5000);
    CHECK(!runtime.VerdictValid && !runtime.VerdictSatisfied);

    NodeContract node;
    CHECK(!Interaction(R"({"action": "gossip_select_sequence", "entry": 44202, "menus": [1], "option": 0, "max_attempts": 3, "retry_interval_ms": 1000, "timeout_ms": 1})", node.Interaction));
    CHECK(!Completion(R"({"kind": "any_of", "contracts": [{"kind": "gameobject_despawned", "entry": 203254, "spawn_id": 239510}, {"kind": "aura_present", "entry": 44418, "spell_id": 82705}]})", node.Completion));
    std::vector<std::uint32_t> entries = ObservedCreatureEntries(node);
    CHECK(entries.size() == 2 && entries[0] == 44202 && entries[1] == 44418);
    NodeContract empty;
    CHECK(!empty.Declared() && ObservedCreatureEntries(empty).empty());

    // Sorted rows: the nested completion kind precedes the row kind.
    char const* row = R"({"completion_contract": {"entry": 41442, "kind": "boss_summoned"}, "kind": "interaction", "label": "x"})";
    CHECK(BotValidationRouteNativeJson::TopLevelString(row, "kind", "fallback") == "interaction");
    CHECK(BotValidationRouteNativeJson::TopLevelString("{broken", "kind", "fallback") == "fallback");
    return failures ? 1 : 0;
}
''')


def test_every_committed_route_contract_parses_and_matches_its_kind(tmp_path: Path) -> None:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    nodes = []
    for group in ("scenarios", "diagnostic_scenarios"):
        for scenario in config[group]:
            for row in scenario["route"]:
                nodes.append(row)
    body = []
    for row in nodes:
        parts = []
        for field, parser in (
            ("interaction_contract", "Interaction"),
            ("completion_contract", "Completion"),
            ("transport_contract", "Transport"),
        ):
            if field in row:
                literal = json.dumps(json.dumps(row[field]))
                parts.append(f"CHECK(!{parser}({literal}, node.{parser}));")
        if not parts:
            continue
        kind = json.dumps(row["kind"])
        body.append("{ NodeContract node; " + " ".join(parts)
                    + f" CHECK(!ValidateNodeShape({kind}, node.Interaction, node.Completion, node.Transport)); }}")
    # 9 full-raid rows (incl. the elevator and the arena platform) + 8 shard rows.
    assert len(body) >= 17
    assert sum('CHECK(!Transport(' in line for line in body) == 3
    _compile_and_run(tmp_path, PRELUDE + "int main()\n{\n" + "\n".join(body)
                     + "\n    return failures ? 1 : 0;\n}\n")


def test_legacy_regex_kind_matches_top_level_kind_for_accepted_magmaw_rows() -> None:
    """The structural kind read is neutral for rows without nested kinds."""

    routes = ROOT / "dataset/validation_scenarios/validation_routes.jsonl"
    if not routes.exists():
        import pytest
        pytest.skip("validation_routes.jsonl not materialized")
    pattern = re.compile(r'"kind"\s*:\s*"([^"]*)"')
    checked = 0
    for line in routes.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["scenario_id"] != "blackwing_descent_10n_magmaw_diagnostic":
            continue
        text = json.dumps(row, indent=2, sort_keys=True)
        assert pattern.search(text).group(1) == row["kind"]
        checked += 1
    assert checked == 4


def test_route_state_includes_only_the_data_only_contract_types(tmp_path: Path) -> None:
    """RouteState.h reaches ~180 TUs: it may include only the small data header."""

    bots = ROOT / "src/server/game/Bots"
    route_state = (bots / "BotWorldPopulationMgrRouteState.h").read_text(encoding="utf-8")
    assert '#include "Bots/BotValidationRouteNativeTypes.h"' in route_state
    for heavy in ("BotValidationRouteNativeLogic.h", "BotValidationRouteNativeContract.h",
                  "BotValidationRouteNativeJson.h"):
        assert heavy not in route_state
    types = (bots / "BotValidationRouteNativeTypes.h").read_text(encoding="utf-8")
    assert len(types.splitlines()) < 300
    includes = re.findall(r'#include [<"]([^>"]+)[>"]', types)
    assert includes and all("/" not in name and not name.endswith(".h") for name in includes)
    for logic in ("ElectOwner", "DecideInteraction", "EvaluateCompletion", "DecideTransportStep", "Parse"):
        assert logic not in re.sub(r"//.*", "", types)
    _compile_and_run(tmp_path, '#include "Bots/BotValidationRouteNativeTypes.h"\nint main() { return BotValidationRouteNative::NodeContract().Declared() ? 1 : 0; }\n')


def test_stranded_check_ignores_walking_members_and_confirms_real_strandings(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PRELUDE + r'''
int main()
{
    TransportContract ride;
    CHECK(!Transport(R"({"entry": 203716, "board_transport_z": 186.551, "exit_transport_z": 73.8806, "wait_point": [-256.35, -224.605, 190.163], "board_point": [-247.349, -224.605, 190.028], "exit_point": [-224.0, -224.605, 76.8211], "timeout_ms": 240000})", ride));

    // A member walking its spline toward the wait point may sit above the
    // vmap floor between path points: never a stranding.
    TransportMemberState walker;
    TransportMemberObservation w;
    w.Alive = true; w.TransportPresent = true; w.Moving = true;
    w.DistanceToWait = 12.0f; w.DistanceToBoard = 20.0f;
    for (std::uint64_t now = 0; now <= 3000; now += 250)
    {
        w.NowMs = now;
        TransportDecision decision = DecideTransportStep(ride, w, walker);
        CHECK(decision.Step == TransportStep::MoveToWait);
    }
    CHECK(walker.FloorlessObservations == 0 && !walker.PlatformFloorSeen);
    // Even after it stood on the platform, walking or falling is not a stranding.
    walker.PlatformFloorSeen = true;
    for (std::uint64_t now = 0; now <= 3000; now += 250)
    {
        w.NowMs = now;
        w.Falling = now % 500 == 0;
        w.Moving = !w.Falling;
        CHECK(DecideTransportStep(ride, w, walker).Step != TransportStep::Fail);
    }
    // Stationary and floorless without ever having stood on the platform:
    // diagnostic hold, never a failure.
    TransportMemberState unverified;
    TransportMemberObservation u;
    u.Alive = true; u.TransportPresent = true;
    for (std::uint64_t now = 0; now <= 3000; now += 250)
    {
        u.NowMs = now;
        TransportDecision decision = DecideTransportStep(ride, u, unverified);
        CHECK(decision.Step == TransportStep::Hold && decision.Reason == "transport_member_floor_unverified");
    }
    // Walking off the platform onto static ground clears the latch.
    TransportMemberState cleared;
    TransportMemberObservation c;
    c.Alive = true; c.TransportPresent = true; c.TransportFloorUnderfoot = true;
    DecideTransportStep(ride, c, cleared);
    CHECK(cleared.PlatformFloorSeen);
    c.TransportFloorUnderfoot = false; c.StaticFloorUnderfoot = true;
    DecideTransportStep(ride, c, cleared);
    CHECK(!cleared.PlatformFloorSeen);

    // Truly stranded: stood on the platform, now stationary with no floor.
    TransportMemberState stranded;
    TransportMemberObservation s;
    s.Alive = true; s.TransportPresent = true; s.TransportFloorUnderfoot = true;
    s.DistanceToBoard = 0.2f; s.NowMs = 1000;
    CHECK(DecideTransportStep(ride, s, stranded).Step == TransportStep::Board);
    s.TransportFloorUnderfoot = false;
    // Three quick observations are not enough time.
    for (std::uint64_t now : { 1100u, 1150u, 1200u })
    {
        s.NowMs = now;
        CHECK(DecideTransportStep(ride, s, stranded).Step == TransportStep::Hold);
    }
    // Any movement in between restarts the confirmation.
    s.Moving = true; s.NowMs = 1300;
    CHECK(DecideTransportStep(ride, s, stranded).Step != TransportStep::Fail);
    CHECK(stranded.FloorlessObservations == 0);
    s.Moving = false;
    for (std::uint64_t now : { 2000u, 2200u })
    {
        s.NowMs = now;
        CHECK(DecideTransportStep(ride, s, stranded).Step == TransportStep::Hold);
    }
    s.NowMs = 2450;
    TransportDecision fail = DecideTransportStep(ride, s, stranded);
    CHECK(fail.Step == TransportStep::Fail && fail.Reason == "transport_member_stranded_without_floor");
    return failures ? 1 : 0;
}
''')


def test_rest_window_gate_stops_or_retreats_a_running_walk(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PRELUDE + r'''
int main()
{
    TransportContract ride;
    CHECK(!Transport(R"({"entry": 203716, "board_transport_z": 186.551, "exit_transport_z": 73.8806, "wait_point": [-256.35, -224.605, 190.163], "board_point": [-247.349, -224.605, 190.028], "exit_point": [-224.0, -224.605, 76.8211], "timeout_ms": 240000})", ride));
    TransportMemberState state;
    TransportMemberObservation o;
    o.Alive = true; o.TransportPresent = true; o.StaticFloorUnderfoot = true;
    o.ReadyToBoard = true; o.Moving = true;
    o.DistanceToWait = 4.0f; o.DistanceToBoard = 5.0f;
    o.RestRemainingMs = 1000; o.TravelToBoardMs = 900;
    // Mid-walk off the platform: retreat to the wait point.
    TransportDecision decision = DecideTransportStep(ride, o, state);
    CHECK(decision.Step == TransportStep::MoveToWait && decision.Reason == "transport_rest_window_short_retreat");
    // Already at the wait point: stop the running spline instead of holding.
    o.DistanceToWait = 0.5f;
    decision = DecideTransportStep(ride, o, state);
    CHECK(decision.Step == TransportStep::Stop && decision.Reason == "transport_rest_window_short_stop");
    // Standing still: hold.
    o.Moving = false;
    CHECK(DecideTransportStep(ride, o, state).Reason == "transport_rest_window_too_short");
    // Already over the platform's own surface: stop there and board.
    o.Moving = true; o.StaticFloorUnderfoot = false; o.TransportFloorUnderfoot = true;
    CHECK(DecideTransportStep(ride, o, state).Step == TransportStep::Stop);
    o.Moving = false;
    CHECK(DecideTransportStep(ride, o, state).Step == TransportStep::Board);
    // Not ready while still walking at the wait point: stop.
    TransportMemberState idle;
    TransportMemberObservation n;
    n.Alive = true; n.TransportPresent = true; n.StaticFloorUnderfoot = true;
    n.Moving = true; n.DistanceToWait = 0.5f;
    CHECK(DecideTransportStep(ride, n, idle).Step == TransportStep::Stop);
    return failures ? 1 : 0;
}
''')
