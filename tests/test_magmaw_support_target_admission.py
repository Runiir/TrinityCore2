from __future__ import annotations

import subprocess
import pytest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def compile_probe(tmp_path: Path, source_text: str) -> Path:
    source = tmp_path / "magmaw_support_target_admission.cpp"
    binary = tmp_path / "magmaw_support_target_admission"
    source.write_text(source_text, encoding="utf-8")
    subprocess.run(
        [
            "g++",
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(tmp_path),
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
            "-I",
            str(ROOT / "dep/g3dlite/include"),
            str(source),
            "-o",
            str(binary),
        ],
        cwd=ROOT,
        check=True,
    )
    return binary


@pytest.mark.parametrize("revision", [None, "26c536140a4e23c43d3d8e5016d3d1aa0463a716"])
def test_native_opportunity_and_production_support_selector(
    tmp_path: Path, revision,
) -> None:
    if revision:
        relative = Path("Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotAdaptiveMagmawStrategySupport.h")
        frozen = tmp_path / relative
        frozen.parent.mkdir(parents=True)
        frozen.write_text(subprocess.check_output(
            ["git", "show", f"{revision}:src/server/game/{relative}"], cwd=ROOT, text=True))
    binary = compile_probe(
        tmp_path,
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotAdaptiveMagmawStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawDamageTargetBinding.h"
#include <cassert>
#include <optional>

using namespace BotEncounter;

std::string ObjectGuid::ToString() const
{
    return std::to_string(GetRawValue());
}

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

struct NativeUnit
{
    ObjectGuid Guid;
    bool InWorld = true;
    bool Alive = true;
    bool Attackable = true;
    bool LineOfSight = true;
    int Map = 669;
    int Instance = 1;
    float Distance = 0.0f;

    ObjectGuid GetGUID() const { return Guid; }
    bool IsInWorld() const { return InWorld; }
    bool IsAlive() const { return Alive; }
    int GetMap() const { return Map; }
    int GetInstanceId() const { return Instance; }
    bool IsValidAttackTarget(NativeUnit const* target) const
    {
        return target && target->Attackable;
    }
    bool IsWithinLOSInMap(NativeUnit const*) const { return LineOfSight; }
    float GetExactDist(NativeUnit const*) const { return Distance; }
};

struct NativeContext
{
    struct NativeState
    {
        ObjectGuid TargetGuid;
    } State;
    NativeUnit* Bot = nullptr;
    NativeUnit* Target = nullptr;
};

static AdaptiveMagmawPlan Propose(AdaptiveMagmawStrategy const& strategy,
    Blackboard const& board, ObjectGuid actor,
    MagmawSupportTargetOpportunities const& opportunities,
    MagmawLaneTransitionState* lane = nullptr)
{
    return strategy.Propose(board, actor, "dps", nullptr, false, false,
        lane, nullptr, nullptr, std::nullopt,
        AdaptiveMagmawStrategy::DefaultMovementProducerOrder, nullptr,
        nullptr, nullptr, nullptr, &opportunities);
}

int main()
{
    NativeUnit nativeActor;
    NativeUnit nativeTarget;
    std::vector<MagmawStaticDamageRange> const legalRanges{
        { 5.0f, 40.0f } };
    nativeActor.Distance = 4.0f;
    assert(!ObserveMagmawStaticDamageOpportunity(
        &nativeActor, &nativeTarget, legalRanges));
    nativeActor.Distance = 5.0f;
    assert(ObserveMagmawStaticDamageOpportunity(
        &nativeActor, &nativeTarget, legalRanges));
    nativeActor.Distance = 40.0f;
    assert(ObserveMagmawStaticDamageOpportunity(
        &nativeActor, &nativeTarget, legalRanges));
    nativeActor.Distance = 41.0f;
    assert(!ObserveMagmawStaticDamageOpportunity(
        &nativeActor, &nativeTarget, legalRanges));
    nativeActor.Distance = 20.0f;
    nativeActor.LineOfSight = false;
    assert(!ObserveMagmawStaticDamageOpportunity(
        &nativeActor, &nativeTarget, legalRanges));
    nativeActor.LineOfSight = true;
    nativeTarget.Instance = 2;
    assert(!ObserveMagmawStaticDamageOpportunity(
        &nativeActor, &nativeTarget, legalRanges));
    nativeTarget.Instance = 1;

    for (int invalid = 0; invalid != 4; ++invalid)
    {
        NativeUnit target = nativeTarget;
        if (invalid == 0) target.Alive = false;
        if (invalid == 1) target.InWorld = false;
        if (invalid == 2) target.Attackable = false;
        if (invalid == 3) target.Map = 1;
        assert(!ObserveMagmawStaticDamageOpportunity(&nativeActor, &target, legalRanges));
    }
    assert(!ObserveMagmawStaticDamageOpportunity(
        static_cast<NativeUnit*>(nullptr), &nativeTarget, legalRanges));
    assert(!ObserveMagmawStaticDamageOpportunity(
        &nativeActor, static_cast<NativeUnit*>(nullptr), legalRanges));

    Blackboard board;
    board.CurrentScope = Scope{
        "enc003", 7, 0, 1, "bwd.magmaw.encounter", 669, 1, "magmaw" };
    board.Route.NodeId = "bwd.magmaw.encounter";
    board.NativeBossState = "in_progress";
    board.ObservedAtMs = 1788989689519;
    board.Players = {
        Player(30006, "fire_mage", { 20.0f, -20.0f, 210.0f }),
        Player(30009, "marksmanship_hunter", { 20.0f, 20.0f, 210.0f }),
        Player(30007, "fire_mage", { 0.0f, 0.0f, 210.0f }) };
    ActorSnapshot boss = Hostile(AdaptiveMagmawStrategy::BossEntry, 39,
        { 18.0f, 0.0f, 210.0f });
    boss.InCombat = true;
    boss.VictimGuid = board.Players.front().Guid;
    ActorSnapshot blocked = Hostile(
        AdaptiveMagmawStrategy::ParasiteAltEntry, 215,
        { 20.0f, 0.0f, 210.0f });
    ActorSnapshot legal = Hostile(
        AdaptiveMagmawStrategy::ParasiteEntry, 216,
        { 24.0f, 0.0f, 210.0f });
    board.Hostiles = { boss, blocked, legal };

    AdaptiveMagmawStrategy strategy;
    ObjectGuid const supportActor = board.Players.back().Guid;
    MagmawSupportTargetOpportunities bodyOnly;
    bodyOnly.Admit(boss.Guid);

    // Historical ENC-003 control: the nearest optional parasite is blocked,
    // so the observed legal body remains attackable.
    AdaptiveMagmawPlan bodyFallback = Propose(
        strategy, board, supportActor, bodyOnly);
    assert(bodyFallback.DamageTarget == boss.Guid);
    assert(bodyFallback.ParasiteCombat.SupportTargetGuid.IsEmpty());

    // A farther legal parasite wins over the blocked nearest parasite.
    MagmawSupportTargetOpportunities legalAlternative = bodyOnly;
    legalAlternative.Admit(legal.Guid);
    AdaptiveMagmawPlan alternative = Propose(
        strategy, board, supportActor, legalAlternative);
    assert(alternative.DamageTarget == legal.Guid);
    assert(alternative.ParasiteCombat.SupportTargetGuid == legal.Guid);

    // A current legal support target is retained while another legal parasite
    // becomes nearer, avoiding a per-tick target flip.
    Blackboard retained = board;
    retained.BotTargets[supportActor].DamageTarget = legal.Guid;
    retained.Hostiles[1].Position = { 18.0f, 0.0f, 210.0f };
    legalAlternative.Admit(blocked.Guid);
    AdaptiveMagmawPlan retainedPlan = Propose(
        strategy, retained, supportActor, legalAlternative);
    assert(retainedPlan.DamageTarget == legal.Guid);

    // No observed parasite or body opportunity leaves the optional selector
    // empty instead of binding a target that support movement may not chase.
    MagmawSupportTargetOpportunities noneLegal;
    AdaptiveMagmawPlan none = Propose(
        strategy, board, supportActor, noneLegal);
    assert(none.DamageTarget.IsEmpty());
    assert(none.ClearOptionalDamageTarget);
    assert(none.ParasiteCombat.SupportTargetGuid.IsEmpty());

    // DPS-043: fixed Mage and Hunter baiters use actual native opportunity
    // admission for damage, while their mandatory assignments remain intact.
    MagmawSupportTargetOpportunities baitOpportunities = bodyOnly;
    nativeActor.Distance = 20;nativeActor.LineOfSight = false;
    assert(!ObserveMagmawStaticDamageOpportunity(&nativeActor, &nativeTarget, legalRanges));
    nativeActor.Distance = 24;nativeActor.LineOfSight = true;
    if (ObserveMagmawStaticDamageOpportunity(&nativeActor, &nativeTarget, legalRanges))
        baitOpportunities.Admit(legal.Guid);
    for (ObjectGuid baiter : {board.Players[0].Guid, board.Players[1].Guid})
    {
        AdaptiveMagmawPlan bait = Propose(strategy, board, baiter, baitOpportunities);
        NativeUnit nativeBaiter;nativeBaiter.Guid = baiter;
        NativeUnit nativeLegal;nativeLegal.Guid = legal.Guid;
        NativeUnit nativeBlocked;nativeBlocked.Guid = blocked.Guid;
        NativeContext baitContext; baitContext.Bot = &nativeBaiter;
        // Bind the actual selection before checking identity: old26 binds215.
        assert(BindMagmawDamageTarget(baitContext, bait.DamageTarget,
            bait.ClearOptionalDamageTarget,
            bait.DamageTarget == legal.Guid ? &nativeLegal : &nativeBlocked)
            == MagmawDamageTargetBindResult::Bound);
        assert(baitContext.State.TargetGuid == legal.Guid);
        assert(bait.ParasiteCombat.IsAssignedBaiter(baiter));
        assert(bait.ParasiteCombat.AllowsParasiteTarget(baiter, blocked.Guid));
        assert(bait.ParasiteCombat.SupportTargetGuid.IsEmpty());
        Blackboard pursued = board;
        pursued.Hostiles[1].VictimGuid = baiter;
        AdaptiveMagmawPlan pursuedPlan = Propose(strategy, pursued, baiter, baitOpportunities);
        assert(pursuedPlan.DamageTarget == legal.Guid);
        assert(pursuedPlan.ParasiteCombat.PersonalThreatGuid == blocked.Guid);
        assert(pursuedPlan.ParasiteCombat.IsAssignedBaiter(baiter));
        AdaptiveMagmawPlan baitBody = Propose(strategy, pursued, baiter, bodyOnly);
        assert(baitBody.DamageTarget == boss.Guid);
        AdaptiveMagmawPlan baitNone = Propose(strategy, pursued, baiter, noneLegal);
        assert(baitNone.DamageTarget.IsEmpty() && baitNone.ClearOptionalDamageTarget);
        assert(baitNone.ParasiteCombat.IsAssignedBaiter(baiter));
        assert(baitNone.ParasiteCombat.PersonalThreatGuid == blocked.Guid);
        assert(BindMagmawDamageTarget(baitContext, baitNone.DamageTarget,
            baitNone.ClearOptionalDamageTarget, static_cast<NativeUnit*>(nullptr))
            == MagmawDamageTargetBindResult::Cleared);
        assert(baitContext.Target == nullptr && baitContext.State.TargetGuid.IsEmpty());
        assert(baitNone.ParasiteCombat.IsAssignedBaiter(baiter));
        assert(baitNone.ParasiteCombat.PersonalThreatGuid == blocked.Guid);
        Blackboard sticky = board;
        sticky.BotTargets[baiter].DamageTarget = legal.Guid;
        MagmawSupportTargetOpportunities bothLegal = baitOpportunities;
        bothLegal.Admit(blocked.Guid);
        assert(Propose(strategy, sticky, baiter, bothLegal).DamageTarget == legal.Guid);
        Blackboard escaping = pursued;
        escaping.Route.NavigationHints = { { 50, 0, 210 } };
        escaping.Hostiles[1].Position = escaping.FindActor(baiter)->Position;
        escaping.Hostiles[1].Position.X += 8.0f;
        MagmawLaneTransitionState legalLane, blockedLane;
        AdaptiveMagmawPlan escapeLegal = Propose(strategy, escaping, baiter, baitOpportunities, &legalLane);
        AdaptiveMagmawPlan escapeBlocked = Propose(strategy, escaping, baiter, noneLegal, &blockedLane);
        assert(escapeLegal.DamageTarget == legal.Guid && escapeBlocked.DamageTarget.IsEmpty());
        assert(escapeLegal.Movement && escapeBlocked.Movement);
        assert(escapeLegal.Movement.Size() == escapeBlocked.Movement.Size());
        auto const& legalMoves = escapeLegal.Movement.Proposals();
        auto const& blockedMoves = escapeBlocked.Movement.Proposals();
        bool contactEscape = false;
        for (size_t i=0; i<legalMoves.size(); ++i)
        {
            contactEscape = contactEscape || legalMoves[i].Id.Mechanic == "parasite_contact_evade";
            assert(legalMoves[i].Id.Mechanic == blockedMoves[i].Id.Mechanic);
            assert(legalMoves[i].ActionPriority == blockedMoves[i].ActionPriority);
        }
        assert(contactEscape);

    }
    // Ordinary DPS retains its separately owned personal-threat obligation.
    Blackboard threatened = board;
    threatened.Hostiles[1].VictimGuid = supportActor;
    AdaptiveMagmawPlan threat = Propose(
        strategy, threatened, supportActor, noneLegal);
    assert(threat.DamageTarget == blocked.Guid);

    // Head priority survives the opportunity gate. When the head hides, the
    // same live observation returns to the eligible body.
    Blackboard exposed = board;
    ActorSnapshot head = Hostile(AdaptiveMagmawStrategy::HeadEntry, 76,
        { 18.0f, 0.0f, 210.0f });
    exposed.Hostiles.push_back(head);
    AdaptiveMagmawPlan headPlan = Propose(
        strategy, exposed, supportActor, bodyOnly);
    assert(headPlan.DamageTarget == head.Guid);
    NativeUnit nativeBot;
    nativeBot.Guid = supportActor;
    NativeUnit nativeHead;
    nativeHead.Guid = head.Guid;
    NativeUnit nativeBody;
    nativeBody.Guid = boss.Guid;
    NativeContext context;
    context.Bot = &nativeBot;
    assert(BindMagmawDamageTarget(context, headPlan.DamageTarget,
        headPlan.ClearOptionalDamageTarget, &nativeHead)
        == MagmawDamageTargetBindResult::Bound);
    assert(context.Target == &nativeHead);
    assert(context.State.TargetGuid == head.Guid);

    Blackboard protectedHead = exposed;
    protectedHead.Hostiles.back().Attackable = false;
    assert(Propose(strategy, protectedHead, supportActor, bodyOnly).DamageTarget == boss.Guid);
    protectedHead.Hostiles.back().Attackable = true;
    protectedHead.Hostiles.back().Selectable = false;
    assert(Propose(strategy, protectedHead, supportActor, bodyOnly).DamageTarget == boss.Guid);
    nativeHead.Attackable = false;
    AdaptiveMagmawPlan hideReturn = Propose(
        strategy, board, supportActor, bodyOnly);
    assert(hideReturn.DamageTarget == boss.Guid);
    assert(BindMagmawDamageTarget(context, hideReturn.DamageTarget,
        hideReturn.ClearOptionalDamageTarget, &nativeBody)
        == MagmawDamageTargetBindResult::Bound);
    assert(context.Target == &nativeBody);
    assert(context.State.TargetGuid == boss.Guid);
    MagmawParasiteCombatContract::ProfileParameters const bodyProfile =
        hideReturn.ParasiteCombat.ResolveProfileParameters(supportActor,
            context.State.TargetGuid,
            MagmawParasiteCombatContract::BossEntry,
            false, false, false);
    assert(bodyProfile.TargetAllowed);

    NativeUnit deadBody = nativeBody;
    deadBody.Alive = false;
    assert(BindMagmawDamageTarget(context, boss.Guid, false, &deadBody)
        == MagmawDamageTargetBindResult::NativeDead);
    NativeUnit invalidBody = nativeBody;
    invalidBody.Attackable = false;
    assert(BindMagmawDamageTarget(context, boss.Guid, false, &invalidBody)
        == MagmawDamageTargetBindResult::NativeInvalid);
    assert(BindMagmawDamageTarget(context, boss.Guid, false,
        static_cast<NativeUnit*>(nullptr))
        == MagmawDamageTargetBindResult::NativeMissing);
    assert(BindMagmawDamageTarget(context, ObjectGuid{}, false,
        static_cast<NativeUnit*>(nullptr))
        == MagmawDamageTargetBindResult::NotRequested);
    assert(BindMagmawDamageTarget(context, ObjectGuid{}, true,
        static_cast<NativeUnit*>(nullptr))
        == MagmawDamageTargetBindResult::Cleared);
    assert(context.Target == nullptr && context.State.TargetGuid.IsEmpty());

    // Opportunity selection does not consume or replace encounter movement.
    Blackboard moving = board;
    ActorSnapshot pillar = Hostile(AdaptiveMagmawStrategy::PillarEntry, 800,
        moving.Players.back().Position);
    moving.Summons.push_back(pillar);
    MagmawSupportTargetOpportunities movementOpportunities = bodyOnly;
    movementOpportunities.Admit(legal.Guid);
    AdaptiveMagmawPlan simultaneous = Propose(
        strategy, moving, supportActor, movementOpportunities);
    assert(simultaneous.DamageTarget == legal.Guid);
    assert(simultaneous.Movement);

    // No observed boss is the pre-existing unowned-node boundary, not a
    // claim that a stale target is legal or that the selector cleared it.
    Blackboard missingBoss = board;
    missingBoss.Hostiles.erase(missingBoss.Hostiles.begin());
    AdaptiveMagmawPlan unowned = Propose(strategy, missingBoss, supportActor, noneLegal);
    assert(!unowned.OwnsNode && unowned.DamageTarget.IsEmpty());

    // With no parasites, the ordinary body path is unchanged even when the
    // optional opportunity view is empty.
    Blackboard noParasites = board;
    noParasites.Hostiles = { boss };
    AdaptiveMagmawPlan ordinaryBody = Propose(
        strategy, noParasites, supportActor, noneLegal);
    assert(ordinaryBody.DamageTarget == boss.Guid);
    assert(!ordinaryBody.ClearOptionalDamageTarget);
}
''',
    )
    result = subprocess.run([str(binary)], cwd=ROOT, capture_output=True, text=True)
    if revision:
        assert result.returncode != 0
        assert "baitContext.State.TargetGuid == legal.Guid" in result.stderr
    else:
        assert result.returncode == 0, result.stderr


def test_production_preparation_observes_and_consumes_opportunities() -> None:
    preparation = (
        ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateBotKernelPreparation.cpp"
    ).read_text(encoding="utf-8")
    assert "ObserveMagmawStaticDamageOpportunity(" in preparation
    assert "ObserveMagmawSupportTargetOpportunities(context.Bot," in preparation
    assert "&magmawSupportOpportunities);" in preparation
    assert "BotEncounter::BindMagmawDamageTarget(context," in preparation
    assert "magmawPlan.ClearOptionalDamageTarget, adaptiveTarget);" in preparation
