from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def test_actual_magmaw_observation_serializes_covered_to_valid_body_return(
    tmp_path: Path,
) -> None:
    source = tmp_path / "magmaw_head_return_observation.cpp"
    binary = tmp_path / "magmaw_head_return_observation"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotAdaptiveMagmawStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawTargetReturnObservation.h"
#include <cassert>
#include <string>

using namespace BotEncounter;
using namespace BotEncounter::MagmawTargetReturnObservation;

static ObjectGuid PlayerGuid(uint32 value)
{
    return ObjectGuid(HighGuid::Player, value);
}

static ActorSnapshot Creature(uint32 entry, uint32 value, bool attackable,
    bool selectable)
{
    ActorSnapshot actor;
    actor.Guid = ObjectGuid(HighGuid::Unit, entry, value);
    actor.Entry = entry;
    actor.Alive = true;
    actor.Attackable = attackable;
    actor.Selectable = selectable;
    actor.InCombat = true;
    return actor;
}

static Blackboard BaseBoard()
{
    Blackboard board;
    board.CurrentScope = Scope{ "head-return", 7, 0, 11,
        "bwd.magmaw.encounter", 669, 3, "magmaw" };
    board.Route.NodeId = "bwd.magmaw.encounter";
    board.NativeBossState = "in_progress";
    board.ObservedAtMs = 1000;
    board.Revision = 20;
    ActorSnapshot bot;
    bot.Guid = PlayerGuid(30008);
    bot.Alive = true;
    bot.Role = "dps";
    bot.ClassSpec = "fire_mage";
    board.Players = { bot };
    return board;
}

int main()
{
    ObjectGuid const actorGuid = PlayerGuid(30008);
    ObjectGuid const staleHead = ObjectGuid(HighGuid::Unit, uint32(42347),
        uint32(76));
    Blackboard covered = BaseBoard();
    covered.Interactables = {
        Creature(41570, 39, false, true),
        Creature(42347, 76, false, false) };
    MagmawFacts coveredFacts;
    coveredFacts.HeadExposed = MagmawTruth::False;
    AdaptiveMagmawPlan coveredPlan = AdaptiveMagmawStrategy().Propose(
        covered, actorGuid, "dps");
    assert(!coveredPlan.OwnsNode && coveredPlan.DamageTarget.IsEmpty());
    Record coveredRecord = Begin(covered, &coveredFacts, 7, 11,
        coveredPlan.OwnsNode, coveredPlan.DamageTarget, staleHead, staleHead,
        staleHead);
    ObserveNative(coveredRecord.Body, true, true, false);
    ObserveNative(coveredRecord.Head, true, true, false);
    Finish(coveredRecord, coveredRecord.Result, staleHead, staleHead);
    std::string coveredJson = BuildJson(coveredRecord, 7, 11, 20,
        "bwd.magmaw.encounter");
    assert(coveredJson.find("\"current\":true") != std::string::npos);
    assert(coveredJson.find("\"bucket\":\"interactables\"")
        != std::string::npos);
    assert(coveredJson.find("\"bind_result\":\"plan_target_empty\"")
        != std::string::npos);

    Blackboard returned = covered;
    returned.Revision = 21;
    returned.ObservedAtMs = 1100;
    returned.Hostiles = { Creature(41570, 39, true, true) };
    returned.Interactables.erase(returned.Interactables.begin());
    MagmawFacts returnedFacts;
    returnedFacts.HeadExposed = MagmawTruth::False;
    AdaptiveMagmawPlan returnedPlan = AdaptiveMagmawStrategy().Propose(
        returned, actorGuid, "dps");
    assert(returnedPlan.OwnsNode);
    assert(returnedPlan.DamageTarget == returned.Hostiles.front().Guid);
    Record returnedRecord = Begin(returned, &returnedFacts, 7, 11,
        returnedPlan.OwnsNode, returnedPlan.DamageTarget, staleHead, staleHead,
        staleHead);
    ObserveNative(returnedRecord.Body, true, true, true);
    ObserveNative(returnedRecord.Head, true, true, false);
    ObserveProposedNative(returnedRecord, true, true, true);
    Finish(returnedRecord, BindResult::Bound, returnedPlan.DamageTarget,
        returnedPlan.DamageTarget);
    std::string returnedJson = BuildJson(returnedRecord, 7, 11, 21,
        "bwd.magmaw.encounter");
    assert(returnedJson.find("\"bucket\":\"hostiles\"")
        != std::string::npos);
    assert(returnedJson.find("\"native_valid_attack_target\":true")
        != std::string::npos);
    assert(returnedJson.find("\"bind_result\":\"bound\"")
        != std::string::npos);
    assert(BuildJson(returnedRecord, 7, 11, 22, "bwd.magmaw.encounter")
        .find("\"current\":false")
        != std::string::npos);
    assert(BuildJson(returnedRecord, 7, 11, 21, "bwd.omnotron.encounter")
        .find("\"current\":false") != std::string::npos);

    Record invalid = Begin(returned, &returnedFacts, 7, 11, true,
        returnedPlan.DamageTarget, staleHead, staleHead, staleHead);
    ObserveNative(invalid.Body, true, true, false);
    ObserveProposedNative(invalid, true, true, false);
    Finish(invalid, BindResult::NativeInvalid, staleHead, staleHead);
    std::string invalidJson = BuildJson(invalid, 7, 11, 21,
        "bwd.magmaw.encounter");
    assert(invalidJson.find("\"bind_result\":\"native_invalid\"")
        != std::string::npos);
    assert(invalidJson.find("\"bind_result\":\"bound\"")
        == std::string::npos);

    Record malformed = returnedRecord;
    malformed.ProposedNativeValidAttackTarget = false;
    std::string malformedJson = BuildJson(malformed, 7, 11, 21,
        "bwd.magmaw.encounter");
    assert(malformedJson.find("\"valid\":false") != std::string::npos);
    assert(malformedJson.find("\"bind_result\":\"invalid_payload\"")
        != std::string::npos);
    assert(malformedJson.find("\"bind_result\":\"bound\"")
        == std::string::npos);
}
'''
    )
    result = subprocess.run(
        [
            "c++",
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(ROOT / "src/server/game"),
            "-I",
            str(ROOT / "src/server/game/Entities/Object"),
            "-I",
            str(ROOT / "src/common"),
            "-I",
            str(ROOT / "src/common/Utilities"),
            "-I",
            str(ROOT / "src/common/Logging"),
            "-I",
            str(ROOT / "src/common/Debugging"),
            str(source),
            "-o",
            str(binary),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    subprocess.run([str(binary)], check=True)


def test_production_capture_is_observation_only_and_exposes_native_tank_stats():
    producer = (
        ROOT
        / "src/server/game/Bots/BotWorldPopulationMgrUpdateBotKernelPreparation.cpp"
    ).read_text()
    diagnosis = (
        ROOT / "src/server/game/Bots/BotWorldPopulationMgrDiagnosis.cpp"
    ).read_text()
    stats = (
        ROOT / "src/server/game/Bots/BotNativeCombatStatsObservation.h"
    ).read_text()

    assert "MagmawTargetReturnObservation::Begin(" in producer
    assert "MagmawTargetReturnObservation::ObserveNative(" in producer
    assert "MagmawTargetReturnObservation::Finish(" in producer
    assert '== "bwd.magmaw.encounter"' in producer
    assert "TargetBindResult::NativeInvalid" in producer
    assert "TargetBindResult::Bound" in producer
    assert '\\"magmaw_target_return\\"' in diagnosis
    assert '\\"native_combat_stats\\"' in diagnosis
    assert "GetTotalAttackPowerValue(BASE_ATTACK)" in stats
    assert "GetAura(76691, bot->GetGUID())" in stats
    assert "vengeance->GetEffect(0)" in stats
    assert (
        "CalculatePct(bot->GetCreateHealth(), 10) + bot->GetStat(STAT_STAMINA)"
        in stats
    )
    assert "CastSpell" not in stats
    assert "RemoveAura" not in stats
    assert len(diagnosis.splitlines()) < 1000
