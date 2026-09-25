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
    std::vector<ActorFact> GameObjects(std::uint32_t entry, std::uint64_t spawnId) const override
    {
        std::vector<ActorFact> out;
        for (ActorFact const& fact : ObjectFacts)
            if ((!entry || fact.Entry == entry) && (!spawnId || fact.SpawnId == spawnId))
                out.push_back(fact);
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


def test_legacy_bwd_contract_shapes_parse_identically(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PRELUDE + r'''
int main()
{
    InteractionContract bell;
    CHECK(!Interaction(R"({"action": "gameobject_use", "entry": 204276})", bell));
    CHECK(bell.Declared && bell.Action == InteractionAction::GameObjectUse);
    CHECK(bell.Target == TargetType::GameObject && bell.Entry == 204276);
    CHECK(bell.LegacyOwner() && !bell.TimeoutMs && !bell.MaxAttempts && !bell.Gather);

    InteractionContract finkle;
    CHECK(!Interaction(R"({"action": "gossip_select_sequence", "entry": 44202, "menus": [11812, 11834, 11835, 11836, 11837], "option": 0})", finkle));
    CHECK(finkle.Menus.size() == 5 && finkle.Menus.front() == 11812 && finkle.Target == TargetType::Any);

    InteractionContract orb;
    CHECK(!Interaction(R"({"action": "gossip_select", "entry": 203254, "menu": 11492, "option": 0})", orb));
    CHECK(orb.Menus.size() == 1 && orb.Menus.front() == 11492 && orb.Option == 0);

    for (char const* text : {
        R"({"kind": "gameobject_selectable", "entry": 204276})",
        R"({"kind": "boss_summoned", "entry": 41442})",
        R"({"kind": "creature_summoned", "entry": 41376})",
        R"({"kind": "aura_present", "entry": 44418, "spell_id": 82705})",
        R"({"kind": "creature_aggressive_with_victim", "entry": 43296})",
        R"({"kind": "creature_grounded_aggressive_or_engaged", "entry": 41442})" })
    {
        CompletionContract completion;
        CHECK(!Completion(text, completion));
        CHECK(completion.Declared);
    }
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
    CHECK(Interaction(R"({"action": "gameobject_use", "entry": 1, "gather": true})", interaction).Detail == "gather_radius_invalid");

    TransportContract transport;
    CHECK(Transport(R"({"entry": 1, "board_point": [1, 2, 3]})", transport).Detail == "board_readiness_ambiguous");
    CHECK(Transport(R"({"entry": 1, "board_stop_frame": 0, "board_transport_z": 1, "board_point": [1, 2, 3]})", transport).Detail == "board_readiness_ambiguous");
    CHECK(Transport(R"({"entry": 1, "board_stop_frame": 0})", transport).Detail == "board_point_missing");
    CHECK(Transport(R"({"entry": 1, "board_stop_frame": 0, "board_point": [1, 2]})", transport).Detail == "field_type_or_range");
    CHECK(Transport(R"({"entry": 1, "board_stop_frame": 0, "board_point": [1, 2, 3], "exit_stop_frame": 1})", transport).Detail == "exit_shape");
    CHECK(Transport(R"({"entry": 1, "board_stop_frame": 0, "board_point": [1, 2, 3], "disembark_point": [1, 2, 3]})", transport).Detail == "exit_shape");

    InteractionContract none;
    CompletionContract noCompletion;
    TransportContract noTransport;
    CHECK(ValidateNodeShape("transport", none, noCompletion, noTransport).Detail == "transport_kind_requires_transport_contract");
    CHECK(!Transport(R"({"entry": 1, "board_stop_frame": 0, "board_point": [1, 2, 3]})", transport));
    CHECK(ValidateNodeShape("descent", none, noCompletion, transport).Detail == "transport_contract_requires_transport_kind");
    CHECK(ValidateNodeShape("interaction", none, noCompletion, noTransport).Detail == "interaction_kind_requires_contract");
    CHECK(!Interaction(R"({"action": "gameobject_use", "entry": 1})", interaction));
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
    CHECK(!Interaction(R"({"action": "gameobject_use", "entry": 1})", legacy));
    // Historical default: the lowest living GUID owns the interaction.
    CHECK(ElectOwner(legacy, members).Owner == 10);

    InteractionContract byRole;
    CHECK(!Interaction(R"({"action": "gameobject_use", "entry": 1, "owner_role": "dps"})", byRole));
    CHECK(ElectOwner(byRole, members).Owner == 20);
    members[1].Alive = false;
    CHECK(ElectOwner(byRole, members).Owner == 30);

    InteractionContract bySlot;
    CHECK(!Interaction(R"({"action": "spellclick", "entry": 5, "owner_roster_slot": 6, "backup_roster_slot": 1})", bySlot));
    OwnerElection election = ElectOwner(bySlot, members);
    CHECK(election.Owner == 40 && election.UsedBackup && election.Reason == "backup_roster_slot");
    members[1].Alive = true;
    election = ElectOwner(bySlot, members);
    CHECK(election.Owner == 20 && !election.UsedBackup);
    members[0].Alive = false;
    members[1].Alive = false;
    CHECK(ElectOwner(bySlot, members).Reason == "interaction_owner_unavailable");

    InteractionContract bounded;
    CHECK(!Interaction(R"({"action": "vehicle_enter", "entry": 5, "seat": 2, "max_attempts": 2, "retry_interval_ms": 1000, "timeout_ms": 5000, "gather": true, "gather_radius_yards": 8.0, "range_yards": 6.0})", bounded));
    CHECK(bounded.Seat == 2 && bounded.Gather && bounded.GatherRadiusYards == 8.0f && bounded.RangeYards == 6.0f);
    AttemptState attempts;
    CHECK(EvaluateAttemptGate(bounded, attempts, 1000, 1000) == AttemptGate::Allowed);
    RecordAttempt(attempts, 1000);
    CHECK(EvaluateAttemptGate(bounded, attempts, 1000, 1500) == AttemptGate::RetryWait);
    CHECK(EvaluateAttemptGate(bounded, attempts, 1000, 2000) == AttemptGate::Allowed);
    RecordAttempt(attempts, 2000);
    CHECK(EvaluateAttemptGate(bounded, attempts, 1000, 3500) == AttemptGate::AttemptsExhausted);
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
    CHECK(DecideInteraction(bounded, observation, AttemptGate::TimedOut).Reason == "native_interaction_timeout");

    InteractionContract gossip;
    CHECK(!Interaction(R"({"action": "gossip_select_sequence", "entry": 44202, "menus": [11812, 11834], "option": 0})", gossip));
    CHECK(DecideInteraction(gossip, observation, AttemptGate::Allowed).Step == InteractionStep::GossipOpen);
    observation.GossipBoundToTarget = true;
    observation.CurrentGossipMenu = 11834;
    decision = DecideInteraction(gossip, observation, AttemptGate::AttemptsExhausted);
    // Continuing an open dialogue is not a new attempt.
    CHECK(decision.Step == InteractionStep::GossipSelect && !decision.CountsAsAttempt);
    observation.CurrentGossipMenu = 99999;
    CHECK(DecideInteraction(gossip, observation, AttemptGate::AttemptsExhausted).Step == InteractionStep::Hold);

    InteractionContract trigger;
    CHECK(!Interaction(R"({"action": "area_trigger", "area_trigger_id": 6581})", trigger));
    InteractionObservation outside;
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

    // Despawn only after the object was observed spawned in this scope.
    CHECK(!Completion(R"({"kind": "gameobject_despawned", "entry": 203254, "spawn_id": 239510})", contract));
    facts.ObjectFacts.clear();
    CHECK(EvaluateCompletion(contract, facts, memory).Reason == "gameobject_never_observed_spawned");
    ActorFact orb; orb.Entry = 203254; orb.SpawnId = 239510; orb.Spawned = true;
    facts.ObjectFacts = { orb };
    CHECK(!EvaluateCompletion(contract, facts, memory).Satisfied);
    facts.ObjectFacts[0].Spawned = false;
    CHECK(EvaluateCompletion(contract, facts, memory).Satisfied);

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

    MemberFact a; a.Guid = 1; a.Alive = true;
    MemberFact b; b.Guid = 2; b.Alive = true; b.Owner = true;
    MemberFact dead; dead.Guid = 3;
    facts.MemberFacts = { a, b, dead };
    CHECK(!Completion(R"({"kind": "on_transport", "transport_entry": 207834})", contract));
    CHECK(!EvaluateCompletion(contract, facts, memory).Satisfied);
    facts.MemberFacts[0].OnTransport = true; facts.MemberFacts[0].TransportEntry = 207834;
    CHECK(EvaluateCompletion(contract, facts, memory).Reason == "members_pending:1/2");
    facts.MemberFacts[1].OnTransport = true; facts.MemberFacts[1].TransportEntry = 207834;
    CHECK(EvaluateCompletion(contract, facts, memory).Satisfied);
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

    // Composite: the orb completes on its despawn or on Nefarian's summon.
    FakeFacts orbFacts;
    CompletionMemory orbMemory;
    CHECK(!Completion(R"({"kind": "any_of", "contracts": [{"kind": "gameobject_despawned", "entry": 203254, "spawn_id": 239510}, {"kind": "creature_summoned", "entry": 41376}]})", contract));
    orbFacts.ObjectFacts = { orb };
    orbFacts.ObjectFacts[0].Spawned = true;
    CHECK(!EvaluateCompletion(contract, orbFacts, orbMemory).Satisfied);
    orbFacts.CreatureFacts = { nefarian };
    CHECK(EvaluateCompletion(contract, orbFacts, orbMemory).Satisfied);
    orbFacts.CreatureFacts.clear();
    orbFacts.ObjectFacts[0].Spawned = false;
    CHECK(EvaluateCompletion(contract, orbFacts, orbMemory).Satisfied);
    CHECK(!Completion(R"({"kind": "all_of", "contracts": [{"kind": "transport_at_stop", "transport_entry": 207834, "stop_frame": 0}, {"kind": "creature_summoned", "entry": 41376}]})", contract));
    CHECK(!EvaluateCompletion(contract, orbFacts, orbMemory).Satisfied);
    return failures ? 1 : 0;
}
''')


def test_transport_boarding_phases_and_footprint(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PRELUDE + r'''
int main()
{
    // BWD lower-wing elevator geometry: display 10407 box, spawn at z 186.5513.
    LocalBox box{ -12.57f, -12.57f, -1.83f, 12.36f, 12.57f, 3.48f, true };
    TransportFact top; top.Present = true; top.Entry = 203716;
    top.PositionX = -241.349f; top.PositionY = -224.6053f; top.PositionZ = 186.5513f;
    Point3 const boardLocal = LocalOffset(-250.35f, -224.6053f, 190.154f, top);
    CHECK(std::fabs(boardLocal.X + 9.001f) < 0.01f && std::fabs(boardLocal.Z - 3.6027f) < 0.01f);
    CHECK(InsideFootprint(boardLocal, box, 0.5f));
    CHECK(!InsideFootprint(LocalOffset(-256.35f, -224.6053f, 190.163f, top), box, 0.5f));
    // Rotation: a transport facing pi maps world +x to local -x.
    TransportFact arena; arena.Present = true; arena.PositionX = -107.2f; arena.PositionY = -224.6f; arena.PositionZ = 7.0f; arena.Orientation = 3.14159265f;
    Point3 const arenaLocal = LocalOffset(-150.0f, -224.6f, 6.6f, arena);
    CHECK(std::fabs(arenaLocal.X - 42.8f) < 0.01f && std::fabs(arenaLocal.Y) < 0.01f);
    CHECK(!InsideFootprint({ 80.0f, 0.0f, 0.0f, true }, { -90, -90, -9, 90, 90, 9, true }, 0.5f));

    TransportContract ride;
    CHECK(!Transport(R"({"entry": 203716, "spawn_id": 235178, "board_transport_z": 186.5513, "exit_transport_z": 73.8809, "level_tolerance_yards": 0.75, "wait_point": [-256.35, -224.6053, 190.163], "board_point": [-250.35, -224.6053, 190.154], "disembark_point": [-241.35, -224.6053, 77.2], "exit_point": [-224.0, -224.6053, 76.8211], "timeout_ms": 240000})", ride));
    CHECK(ride.HasExit() && ride.DisembarkPoint.Valid);
    CHECK(TransportReadyToBoard(ride, top) && !TransportAtExit(ride, top));
    TransportFact bottom = top; bottom.PositionZ = 73.9f;
    CHECK(!TransportReadyToBoard(ride, bottom) && TransportAtExit(ride, bottom));

    TransportMemberState state;
    TransportMemberObservation o;
    o.Alive = true; o.TransportPresent = true;
    o.DistanceToWait = 20.0f; o.DistanceToBoard = 25.0f; o.DistanceToExit = 120.0f;
    CHECK(DecideTransportStep(ride, o, state).Step == TransportStep::MoveToWait);
    o.DistanceToWait = 0.5f;
    CHECK(DecideTransportStep(ride, o, state).Step == TransportStep::Hold);
    o.ReadyToBoard = true;
    CHECK(DecideTransportStep(ride, o, state).Step == TransportStep::MoveToBoard);
    o.InsideFootprint = true; o.DistanceToBoard = 0.4f; o.Moving = true;
    CHECK(DecideTransportStep(ride, o, state).Reason == "transport_board_settling");
    o.Moving = false;
    CHECK(DecideTransportStep(ride, o, state).Step == TransportStep::Board);
    // Platform left before boarding: never stand in the empty shaft footprint.
    o.ReadyToBoard = false;
    CHECK(DecideTransportStep(ride, o, state).Reason == "transport_not_ready_clear_footprint");
    o.ReadyToBoard = true;
    o.OnThisTransport = true;
    CHECK(DecideTransportStep(ride, o, state).Step == TransportStep::HoldAboard);
    CHECK(state.Boarded);
    o.AtExit = true;
    o.DistanceToDisembark = 9.0f;
    CHECK(DecideTransportStep(ride, o, state).Step == TransportStep::MoveToDisembark);
    o.StaticFloorUnderfoot = true;
    CHECK(DecideTransportStep(ride, o, state).Step == TransportStep::Leave);
    o.OnThisTransport = false; o.InsideFootprint = false;
    CHECK(DecideTransportStep(ride, o, state).Step == TransportStep::MoveToExit);
    o.DistanceToExit = 1.0f;
    CHECK(DecideTransportStep(ride, o, state).Step == TransportStep::Done);
    CHECK(MemberTransportDone(ride, false, true, 1.0f));
    CHECK(!MemberTransportDone(ride, true, true, 1.0f));

    TransportContract board;
    CHECK(!Transport(R"({"entry": 207834, "board_stop_frame": 0, "wait_point": [-158.4, -223.467, 41.3544], "board_point": [-150.0, -224.6, 6.6], "arrival_tolerance_yards": 3.0})", board));
    TransportMemberState boardState;
    TransportMemberObservation b;
    b.Alive = true; b.TransportPresent = true; b.OnThisTransport = true;
    CHECK(DecideTransportStep(board, b, boardState).Step == TransportStep::Done);
    CHECK(MemberTransportDone(board, true, true, 0.0f));
    b.OnThisTransport = false; b.TransportAmbiguous = true;
    CHECK(DecideTransportStep(board, b, boardState).Reason == "transport_ambiguous");
    b.TransportAmbiguous = false; b.OnOtherTransportOrVehicle = true;
    CHECK(DecideTransportStep(board, b, boardState).Reason == "transport_member_on_other_transport");
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
    runtime.Enter({ 1, 1, 3 }, 5000);
    CHECK(runtime.Attempt.Attempts == 0 && runtime.StartedAtMs == 5000);

    NodeContract node;
    CHECK(!Interaction(R"({"action": "gossip_select_sequence", "entry": 44202, "menus": [1], "option": 0})", node.Interaction));
    CHECK(!Completion(R"({"kind": "any_of", "contracts": [{"kind": "gameobject_despawned", "entry": 203254}, {"kind": "aura_present", "entry": 44418, "spell_id": 82705}]})", node.Completion));
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
