from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
HELPER = (
    BOTS
    / "Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawBloodlust.h"
)
MODULE = BOTS / "BotWorldPopulationMgrMagmawBloodlust.cpp"
MANAGER = BOTS / "BotWorldPopulationMgr.h"
RUNTIME = BOTS / "BotWorldPopulationMgrRuntimeContracts.h"
CANDIDATES = BOTS / "BotWorldPopulationMgrUpdateBotKernelCandidates.cpp"
EVENTS = BOTS / "BotWorldPopulationMgrEventRecording.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"
SCENARIOS = ROOT / "dataset/validation_scenarios/validation_scenarios.jsonl"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[brace + 1 : index]
    raise AssertionError(f"unterminated function: {signature}")


def test_exact_magmaw_10n_roster_is_the_admitted_diagnostic_roster() -> None:
    scenario = next(
        json.loads(line)
        for line in SCENARIOS.read_text(encoding="utf-8").splitlines()
        if line.strip()
        and json.loads(line)["scenario_id"]
        == "blackwing_descent_10n_magmaw_diagnostic"
    )
    roster = [
        (member["roster_slot_id"], member["role"], member["class_spec"])
        for member in scenario["roster_identity"]
    ]
    assert len(roster) == 10
    assert roster.count(("raid_dps_5", "dps", "elemental_shaman")) == 1

    source = text(MODULE)
    assert "ValidationRouteManifest.front().ExpectedRoster" in source
    assert 'DiagnosticScenario =\n    "blackwing_descent_10n_magmaw_diagnostic"' in text(HELPER)
    assert 'ValidationRouteScenarioId != DiagnosticScenario' in source
    assert 'AdmissionScenarioId != DiagnosticScenario' in source


def test_first_exposed_head_and_all_raid_lockouts_are_pure_observations() -> None:
    helper = text(HELPER)
    window = function_body(helper, "ObserveFirstHeadWindow(")
    assert 'board.Route.NodeId != EncounterNode' in window
    assert 'board.NativeBossState != "in_progress"' in window
    assert "FindBoss(board)" in window
    assert "FindExposedHead(board)" in window

    head = function_body(helper, "FindExposedHead(")
    assert "actor.Entry == ExposedHeadEntry" in head
    assert "actor.Selectable" in head
    assert "actor.Attackable" in head
    assert "std::sort" in head
    assert "GetRawValue()" in head

    for spell_id in (2825, 32182, 80353, 90355, 57723, 57724, 80354, 95809):
        assert str(spell_id) in helper
    assert "FindRaidLockout(*encounterSnapshot)" in text(MODULE)
    assert "ObservedBloodlustAura(board" in text(MODULE)
    assert "TimingEvidence" in helper
    assert "no_wcl_verification" in helper


def test_bloodlust_is_one_native_cast_with_normal_readiness_and_telemetry() -> None:
    module = text(MODULE)
    body = function_body(module, "SubmitMagmawBloodlustCandidate(")
    runtime = text(RUNTIME)

    assert "MagmawBloodlustSubmitted" in runtime
    assert "MagmawBloodlustAuraObserved" in runtime
    assert "MagmawBloodlustAttemptId" in runtime
    assert "MagmawBloodlustWipeGeneration" in runtime
    assert "MagmawBloodlustRouteGeneration" in runtime
    assert "MagmawBloodlustOwnerGuid" in runtime
    assert "MagmawBloodlustHeadGuid" in runtime

    assert "SelectKnownBloodlustSpell" in body
    assert "HasSpell(BloodlustSpell)" in body
    assert "HasSpell(HeroismSpell)" in body
    assert "TryCastFriendlySpell(originalBot, originalBot,\n                *knownBloodlustSpell" in body
    assert '"submitted_native_spell_"' in body
    assert '"observed_aura_"' in body
    assert "0.0f, spellId, spellId" in body
    assert "knownBloodlustSpell.value_or(0)" in body
    assert '"blocked_" + reason' in body
    assert "MagmawBloodlustSubmitted = true" in body
    assert "MagmawBloodlustHeadGuid != window->HeadGuid" in body
    assert body.index("TryCastFriendlySpell(") < body.index(
        "MagmawBloodlustSubmitted = true"
    )
    assert body.index('"submitted_native_spell_"') > body.index(
        "MagmawBloodlustSubmitted = true"
    )
    assert "Resource::GlobalCooldown" in body
    assert "Resource::Cast" in body
    assert "Resource::Target" in body
    assert "TryCastFriendlySpell" in text(BOTS / "BotWorldPopulationMgrCombatSupport.cpp")

    forbidden = (
        "AddAura(",
        "RemoveSpellCooldown",
        "ResetSpellCooldown",
        "SetCooldown",
        "CastSpell(context.Bot, BloodlustSpell, true)",
        "BotAdaptiveMagmawStrategy.h",
        "BotEncounterBlackboard.cpp",
    )
    assert not any(token in body for token in forbidden)
    assert "SubmitMagmawBloodlustCandidate(context);" in text(CANDIDATES)
    assert "BotWorldPopulationMgrMagmawBloodlust.cpp" in text(CMAKE)
    assert 'observedEvent == "magmaw_bloodlust"' in text(EVENTS)

    attempt = body[body.index("bloodlust.Attempt =") :]
    assert "Cohort()" not in attempt
    assert "Party()" not in attempt
    assert "std::string const cohortId = Cohort().Id" in body
    assert "FindCohort(cohortId) != cohort" in body
    assert "magmaw_bloodlust_stale_context_attempt" in body
    assert "magmaw_bloodlust_stale_context_wipe" in body
    assert "magmaw_bloodlust_stale_context_route" in body
    assert "magmaw_bloodlust_stale_context_snapshot" in body
    assert "currentMagmawBloodlustContextReason," in attempt
    assert "recordBloodlustEvent, findNativeRaidLockout" in attempt
    assert "bloodlust.Attempt = [this, &context" in attempt
    assert "&currentMagmawBloodlustContextReason" not in attempt
    assert "&recordBloodlustEvent" not in attempt
    assert "&findNativeRaidLockout" not in attempt

    for path in (HELPER, MODULE, MANAGER, RUNTIME, CANDIDATES, EVENTS):
        assert len(text(path).splitlines()) < 1000, path


def test_magmaw_spell_selection_and_aura_identity_use_the_same_native_spell(
    tmp_path: Path,
) -> None:
    source = tmp_path / "magmaw_bloodlust_spell_identity.cpp"
    binary = tmp_path / "magmaw_bloodlust_spell_identity"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawBloodlust.h"

#include <cassert>

using namespace BotEncounter;
using namespace BotEncounter::MagmawBloodlust;

static ActorSnapshot Owner(ObjectGuid guid)
{
    ActorSnapshot owner;
    owner.Guid = guid;
    owner.Kind = ActorKind::Player;
    owner.Role = "dps";
    owner.ClassSpec = "elemental_shaman";
    owner.Alive = true;
    return owner;
}

static Blackboard AuraBoard(ObjectGuid ownerGuid, uint32 spellId,
    ObjectGuid casterGuid)
{
    Blackboard board;
    ActorSnapshot owner = Owner(ownerGuid);
    owner.Auras = { AuraSnapshot{ spellId, casterGuid, 1, 0 } };
    board.Players = { owner };
    return board;
}

int main()
{
    std::optional<uint32> const knownHeroism =
        SelectKnownBloodlustSpell(false, true);
    std::optional<uint32> const knownBloodlust =
        SelectKnownBloodlustSpell(true, false);
    std::optional<uint32> const knownNeither =
        SelectKnownBloodlustSpell(false, false);
    assert(knownHeroism && *knownHeroism == HeroismSpell);
    assert(knownBloodlust && *knownBloodlust == BloodlustSpell);
    assert(!knownNeither);

    ObjectGuid const ownerGuid(HighGuid::Player, uint32(30010));
    ObjectGuid const wrongCaster(HighGuid::Player, uint32(30011));

    Blackboard heroism = AuraBoard(ownerGuid, HeroismSpell, ownerGuid);
    assert(ObservedBloodlustAura(heroism, ownerGuid, knownHeroism));
    assert(!ObservedBloodlustAura(heroism, ownerGuid, knownBloodlust));
    assert(!ObservedBloodlustAura(heroism, ownerGuid, knownNeither));

    Blackboard bloodlust = AuraBoard(ownerGuid, BloodlustSpell, ownerGuid);
    assert(ObservedBloodlustAura(bloodlust, ownerGuid, knownBloodlust));
    assert(!ObservedBloodlustAura(bloodlust, ownerGuid, knownHeroism));

    Blackboard wrongCasterBoard = AuraBoard(ownerGuid, HeroismSpell,
        wrongCaster);
    assert(!ObservedBloodlustAura(wrongCasterBoard, ownerGuid,
        knownHeroism));

    Blackboard wrongOwnerBoard = AuraBoard(wrongCaster, HeroismSpell,
        ownerGuid);
    assert(!ObservedBloodlustAura(wrongOwnerBoard, ownerGuid,
        knownHeroism));
    return 0;
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            "g++",
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(ROOT / "src/server/game"),
            "-I",
            str(ROOT / "src/server/game/Entities/Object"),
            "-I",
            str(ROOT / "src/server/shared"),
            "-I",
            str(ROOT / "src/common"),
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_production_candidate_roster_gate_uses_declared_composition(tmp_path):
    module = text(MODULE)
    start = module.index("    auto exactRosterAndOwner =")
    end = module.index("\n    std::optional<ObjectGuid> const owner", start)
    gate = module[start:end]
    fixture = json.loads((ROOT / "experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json").read_text())
    bots = fixture["shards"][0]["bots"]
    members = ",".join("{" + ",".join((json.dumps(bot["canonical_roster_slot_id"]), json.dumps(bot["role"]), json.dumps(bot["class_spec"]), str(bot["character_guid"]))) + "}" for bot in bots)
    program = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <vector>
using uint32 = std::uint32_t;
constexpr char ElementalShamanSpec[]="elemental_shaman";
struct ObjectGuid { uint32 Value=0; bool IsEmpty() const { return !Value; } uint32 GetCounter() const { return Value; } };
struct RaidRosterSlot { std::string RosterSlotId,Role,ClassSpec; ObjectGuid Guid; bool Active=true,LeaseOwned=true; };
struct Identity { std::string RosterSlotId,Role,ClassSpec; uint32 Guid; };
struct Node { std::vector<Identity> ExpectedRoster; };
struct Party { std::vector<Node> ValidationRouteManifest; };
struct Raid { std::map<uint32,RaidRosterSlot> RosterByGuid; };
std::optional<ObjectGuid> candidateOwner(Raid* raid, Party* party) {
'''+gate+r'''
 return exactRosterAndOwner();
}
int main() {
 Party party; Raid raid;
 party.ValidationRouteManifest.push_back({{'''+members+r'''}});
 for (auto const& row:party.ValidationRouteManifest.front().ExpectedRoster)
   raid.RosterByGuid.emplace(row.Guid,RaidRosterSlot{row.RosterSlotId,row.Role,row.ClassSpec,{row.Guid}});
 auto owner=candidateOwner(&raid,&party);
 assert(owner && owner->Value==30010);
 raid.RosterByGuid.at(30001).Role="tank";
 assert(!candidateOwner(&raid,&party));
 raid.RosterByGuid.at(30001).Role="dps";
 raid.RosterByGuid.at(30001).ClassSpec="fire_mage";
 assert(!candidateOwner(&raid,&party));
 raid.RosterByGuid.at(30001).ClassSpec="balance_druid";
 raid.RosterByGuid.at(30001).LeaseOwned=false;
 assert(!candidateOwner(&raid,&party));
 raid.RosterByGuid.at(30001).LeaseOwned=true;
 auto valid=party.ValidationRouteManifest.front().ExpectedRoster;
 party.ValidationRouteManifest.front().ExpectedRoster[0]=valid[1];
 assert(!candidateOwner(&raid,&party));
 party.ValidationRouteManifest.front().ExpectedRoster=valid;
 // Existing two-tank declarations remain supported.
 party.ValidationRouteManifest.front().ExpectedRoster[0].Role="tank";
 party.ValidationRouteManifest.front().ExpectedRoster[0].ClassSpec="protection_paladin";
 raid.RosterByGuid.at(30001).Role="tank";
 raid.RosterByGuid.at(30001).ClassSpec="protection_paladin";
 assert(candidateOwner(&raid,&party));
 party.ValidationRouteManifest.clear();
 assert(!candidateOwner(&raid,&party));
}
'''
    source = tmp_path / "candidate_roster.cpp"
    source.write_text(program)
    binary = tmp_path / "candidate_roster"
    subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", str(source), "-o", str(binary)], check=True, capture_output=True)
    subprocess.run([str(binary)], check=True, capture_output=True)
