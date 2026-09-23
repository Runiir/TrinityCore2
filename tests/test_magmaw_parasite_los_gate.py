"""DPS-065: ranged DPS take a pursuing Lava Parasite only when they can hit it.

Magmaw 10N Balance 30001 selected the parasite chasing it even without line of
sight: Insect Swarm, Moonfire and Starfire failed on LOS (8 in k4, 11 in k5),
each failure blocked the spell for 5 s and walked the actor toward the
parasite. Elemental 30010 showed the same failures (about 14 s in b2 k1).

The production selector now admits a ranged actor's personal threat only when
it is in the same native static damage opportunity set that already gates the
baiter and support targets. These replays drive the production strategy.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MAGMAW = Path("Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw")
SUPPORT = ROOT / "src/server/game" / MAGMAW / "BotAdaptiveMagmawStrategySupport.h"
OBSERVATIONS = ROOT / "src/server/game" / MAGMAW / "BotMagmawObservations.h"
PREPARATION = ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateBotKernelPreparation.cpp"
# Last revision of the selector before the LOS gate.
PRE_GATE_REVISION = "a63322819480c3b9cfcb205af606371198c537d8"

PROBE = r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotAdaptiveMagmawStrategy.h"
#include <cassert>
#include <cstdio>
#include <optional>

using namespace BotEncounter;

std::string ObjectGuid::ToString() const
{
    return std::to_string(GetRawValue());
}

#define CHECK(expr) do { if (!(expr)) { std::fprintf(stderr, "CHECK failed: %s\n", #expr); return 1; } } while (0)

static ActorSnapshot Player(uint32 guid, char const* spec, Vector3 position)
{
    ActorSnapshot actor;
    actor.Guid = ObjectGuid(HighGuid::Player, guid);
    actor.Kind = ActorKind::Player;
    actor.Role = "dps";
    actor.ClassSpec = spec;
    actor.Position = position;
    actor.HealthPct = 100.0f;
    actor.Alive = true;
    return actor;
}

static ActorSnapshot Hostile(uint32 entry, uint32 guid, Vector3 position)
{
    ActorSnapshot actor;
    actor.Guid = ObjectGuid(HighGuid::Unit, entry, guid);
    actor.Entry = entry;
    actor.Kind = ActorKind::Hostile;
    actor.Position = position;
    actor.HealthPct = 100.0f;
    actor.Alive = true;
    actor.Attackable = true;
    actor.Selectable = true;
    return actor;
}

static AdaptiveMagmawPlan Propose(Blackboard const& board, ObjectGuid actor,
    MagmawSupportTargetOpportunities const* opportunities,
    MagmawParasiteHazardState* hazard = nullptr)
{
    AdaptiveMagmawStrategy strategy;
    return strategy.Propose(board, actor, "dps", nullptr, false, false,
        nullptr, hazard, nullptr, std::nullopt,
        AdaptiveMagmawStrategy::DefaultMovementProducerOrder, nullptr,
        nullptr, nullptr, nullptr, opportunities);
}

int main()
{
    Blackboard board;
    board.CurrentScope = Scope{
        "dps065", 7, 0, 1, "bwd.magmaw.encounter", 669, 1, "magmaw" };
    board.Route.NodeId = "bwd.magmaw.encounter";
    board.NativeBossState = "in_progress";
    board.ObservedAtMs = 1790000000000;
    board.Players = {
        Player(30006, "fire_mage", { 20.0f, -20.0f, 210.0f }),
        Player(30009, "marksmanship_hunter", { 20.0f, 20.0f, 210.0f }),
        Player(30001, "balance_druid", { 0.0f, 0.0f, 210.0f }),
        Player(30010, "elemental_shaman", { 0.0f, 40.0f, 210.0f }),
        Player(30008, "assassination_rogue", { 60.0f, 0.0f, 210.0f }) };
    ObjectGuid const mage = board.Players[0].Guid;
    ObjectGuid const balance = board.Players[2].Guid;
    ObjectGuid const elemental = board.Players[3].Guid;
    ObjectGuid const rogue = board.Players[4].Guid;

    ActorSnapshot boss = Hostile(AdaptiveMagmawStrategy::BossEntry, 39,
        { 30.0f, 0.0f, 210.0f });
    boss.InCombat = true;
    boss.VictimGuid = mage;
    // A parasite pursuing the Balance druid from 20 yd.
    ActorSnapshot pursuer = Hostile(AdaptiveMagmawStrategy::ParasiteEntry, 501,
        { 0.0f, -20.0f, 210.0f });
    pursuer.VictimGuid = balance;
    board.Hostiles = { boss, pursuer };

    MagmawSupportTargetOpportunities hittable;
    hittable.Admit(boss.Guid);
    hittable.Admit(pursuer.Guid);
    MagmawSupportTargetOpportunities blocked;
    blocked.Admit(boss.Guid);

    // 1. Hittable threat: targeted exactly as before.
    AdaptiveMagmawPlan hit = Propose(board, balance, &hittable);
    CHECK(hit.DamageTarget == pursuer.Guid);
    CHECK(hit.ParasiteCombat.PersonalThreatGuid == pursuer.Guid);
    CHECK(!hit.ClearOptionalDamageTarget);

    // 2. Threat out of line of sight: stay on Magmaw. The contract still
    // records the threat, so escape ownership and area permissions remain.
    AdaptiveMagmawPlan los = Propose(board, balance, &blocked);
    CHECK(los.DamageTarget == boss.Guid);
    CHECK(los.ParasiteCombat.PersonalThreatGuid == pursuer.Guid);
    CHECK(!los.ClearOptionalDamageTarget);
    CHECK(los.ParasiteCombat.TargetAllowed(balance, pursuer.Guid,
        AdaptiveMagmawStrategy::ParasiteEntry));

    // Nothing hittable at all still keeps the boss, not a blocked parasite.
    MagmawSupportTargetOpportunities none;
    AdaptiveMagmawPlan blind = Propose(board, balance, &none);
    CHECK(blind.DamageTarget == boss.Guid);

    // Callers without an opportunity view keep the prior contract.
    AdaptiveMagmawPlan legacy = Propose(board, balance, nullptr);
    CHECK(legacy.DamageTarget == pursuer.Guid);

    // 3. Elemental follows the same ranged gate.
    Blackboard shaman = board;
    shaman.Hostiles[1].VictimGuid = elemental;
    shaman.Hostiles[1].Position = { 0.0f, 55.0f, 210.0f };
    CHECK(Propose(shaman, elemental, &hittable).DamageTarget == pursuer.Guid);
    CHECK(Propose(shaman, elemental, &blocked).DamageTarget == boss.Guid);

    // 4. A contact threat (inside 12 yd, no victim) uses the same gate, and
    // the contact escape is proposed identically either way.
    Blackboard contact = board;
    contact.Hostiles[1].VictimGuid = ObjectGuid{};
    contact.Hostiles[1].Position = { 0.0f, -8.0f, 210.0f };
    MagmawParasiteHazardState hitHazard;
    MagmawParasiteHazardState losHazard;
    AdaptiveMagmawPlan contactHit = Propose(contact, balance, &hittable, &hitHazard);
    AdaptiveMagmawPlan contactLos = Propose(contact, balance, &blocked, &losHazard);
    CHECK(contactHit.DamageTarget == pursuer.Guid);
    CHECK(contactLos.DamageTarget == boss.Guid);
    CHECK(contactHit.Movement && contactLos.Movement);
    CHECK(contactHit.Movement.Size() == contactLos.Movement.Size());
    bool evade = false;
    auto const& hitMoves = contactHit.Movement.Proposals();
    auto const& losMoves = contactLos.Movement.Proposals();
    for (size_t i = 0; i < hitMoves.size(); ++i)
    {
        evade = evade || hitMoves[i].Id.Mechanic == "parasite_contact_evade";
        CHECK(hitMoves[i].Id.Mechanic == losMoves[i].Id.Mechanic);
        CHECK(hitMoves[i].ActionPriority == losMoves[i].ActionPriority);
    }
    CHECK(evade);

    // 5. Melee DPS opportunity ranges exclude melee-range actions, so the
    // melee contract is unchanged: its pursuing parasite stays eligible.
    Blackboard melee = board;
    melee.Hostiles[1].VictimGuid = rogue;
    melee.Hostiles[1].Position = { 60.0f, -10.0f, 210.0f };
    CHECK(Propose(melee, rogue, &blocked).DamageTarget == pursuer.Guid);

    // 6. Baiter branch unchanged: it already refuses a blocked parasite.
    Blackboard bait = board;
    bait.Hostiles[1].VictimGuid = mage;
    bait.Hostiles[1].Position = { 20.0f, -30.0f, 210.0f };
    ActorSnapshot legal = Hostile(AdaptiveMagmawStrategy::ParasiteAltEntry, 502,
        { 26.0f, -26.0f, 210.0f });
    bait.Hostiles.push_back(legal);
    MagmawSupportTargetOpportunities baitLegal;
    baitLegal.Admit(boss.Guid);
    baitLegal.Admit(legal.Guid);
    AdaptiveMagmawPlan baitPlan = Propose(bait, mage, &baitLegal);
    CHECK(baitPlan.DamageTarget == legal.Guid);
    CHECK(baitPlan.ParasiteCombat.IsAssignedBaiter(mage));
    CHECK(Propose(bait, mage, &blocked).DamageTarget == boss.Guid);
    AdaptiveMagmawPlan baitNone = Propose(bait, mage, &none);
    CHECK(baitNone.DamageTarget.IsEmpty() && baitNone.ClearOptionalDamageTarget);
    MagmawSupportTargetOpportunities baitThreat = baitLegal;
    baitThreat.Admit(pursuer.Guid);
    Blackboard nearThreat = bait;
    nearThreat.Hostiles[1].Position = { 20.0f, -24.0f, 210.0f };
    CHECK(Propose(nearThreat, mage, &baitThreat).DamageTarget == pursuer.Guid);

    // 7. The head still wins over every parasite branch.
    Blackboard head = board;
    head.Hostiles.push_back(Hostile(AdaptiveMagmawStrategy::HeadEntry, 76,
        { 30.0f, 0.0f, 210.0f }));
    CHECK(Propose(head, balance, &hittable).DamageTarget
        == head.Hostiles.back().Guid);
    return 0;
}
'''


def _compile(tmp_path: Path, name: str) -> Path:
    source = tmp_path / f"{name}.cpp"
    binary = tmp_path / name
    source.write_text(PROBE, encoding="utf-8")
    result = subprocess.run(
        [
            "g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
            "-I", str(tmp_path),
            "-I", str(ROOT / "src/server/game"),
            "-I", str(ROOT / "src/server/game/Entities/Object"),
            "-I", str(ROOT / "src/common"),
            "-I", str(ROOT / "src/common/Utilities"),
            "-I", str(ROOT / "src/common/Logging"),
            "-I", str(ROOT / "src/common/Debugging"),
            "-I", str(ROOT / "dep/g3dlite/include"),
            str(source), "-o", str(binary),
        ],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return binary


def test_ranged_personal_threat_requires_static_damage_opportunity(tmp_path: Path) -> None:
    binary = _compile(tmp_path, "magmaw_parasite_los_gate")
    result = subprocess.run([str(binary)], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_pre_gate_selector_chases_the_blocked_threat(tmp_path: Path) -> None:
    """The same replay fails on the pre-gate selector at the LOS case."""
    try:
        frozen = subprocess.check_output(
            ["git", "show", f"{PRE_GATE_REVISION}:src/server/game/{MAGMAW}/"
             "BotAdaptiveMagmawStrategySupport.h"],
            cwd=ROOT, text=True, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        pytest.skip("pre-gate revision is not available in this clone")
    target = tmp_path / MAGMAW / "BotAdaptiveMagmawStrategySupport.h"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(frozen, encoding="utf-8")
    binary = _compile(tmp_path, "magmaw_parasite_los_gate_pre")
    result = subprocess.run([str(binary)], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode != 0
    assert "CHECK failed: los.DamageTarget == boss.Guid" in result.stderr


def test_observation_reuses_the_native_opportunity_set() -> None:
    support = SUPPORT.read_text(encoding="utf-8")
    observations = OBSERVATIONS.read_text(encoding="utf-8")
    preparation = PREPARATION.read_text(encoding="utf-8")
    assert "bool PersonalParasiteThreatStaticDamageOpportunity = false;" in observations
    assert ("observed.PersonalParasiteThreatStaticDamageOpportunity =\n"
            "                        supportOpportunities\n"
            "                        && supportOpportunities->Contains(actor.Guid);") in support
    gate = support[support.index("static bool PersonalThreatDamageAdmitted("):]
    gate = gate[:gate.index("\n    }\n")]
    assert "!observed.SupportOpportunitiesObserved" in gate
    assert "!IsRangedParasiteSupportSpec(classSpec)" in gate
    assert "observed.PersonalParasiteThreatStaticDamageOpportunity" in gate
    select = support[support.index("static ObjectGuid SelectDamageTarget("):]
    select = select[:select.index("\n    }\n")]
    assert "&& PersonalThreatDamageAdmitted(observed, classSpec)" in select
    # The escape task still observes every threat, hittable or not.
    assert "observed.PersonalParasiteThreat,\n" in support
    # The opportunity set is the native LOS + range + attackability observation.
    assert "ObserveMagmawStaticDamageOpportunity(" in preparation
    assert "&magmawSupportOpportunities);" in preparation
