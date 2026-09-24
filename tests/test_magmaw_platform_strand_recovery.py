"""HEAL-002/HEAL-003: Magmaw escape/stage destinations stay on the platform,
a failing return path falls back, and an in-range healer heals through Mangle.

Kill b3-0dbce440-k1 (Magmaw 10N). The first parasite wave (33-54 s) chased
the ranged stack at the support anchor (-308.9, -36.5, 211.6); radial escape
legs (20 yd straight away from the pursuer, actor Z, no floor check) walked
six ranged bots north. Offline Detour on the checked-in 669 tiles: north of
x=-305..-312 the navmesh ends at y~-22 (pit edge), north of x=-315..-323 the
nearest polygons are a ledge at z 220-224. The priest 30005 and druid 30003
stood at (-308.5, -20.6, 208.9), off-mesh and 2.9 yd below the route floor,
until ~91 s; warlock 30008 and shaman 30010 stood at (-314.3, -20.5, 211.1)
under the ledge until ~87-91 s. The healers had no line of sight to the tank.

The replays drive the production strategy with a deterministic native probe
that encodes that geometry; the probe is the only native input.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAGMAW = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw"
BOTS = ROOT / "src/server/game/Bots"
INCLUDES = [
    "-I", str(ROOT / "src/server/game"),
    "-I", str(ROOT / "src/server/game/Entities/Object"),
    "-I", str(ROOT / "src/common"),
    "-I", str(ROOT / "src/common/Utilities"),
    "-I", str(ROOT / "src/common/Logging"),
    "-I", str(ROOT / "src/common/Debugging"),
    "-I", str(ROOT / "dep/g3dlite/include"),
]
SOURCES = [
    MAGMAW / "BotMagmawFacts.cpp",
    MAGMAW / "BotMagmawMovementKernelAdapter.cpp",
    MAGMAW / "BotMagmawPersonalParasiteEscapeDiagnostics.cpp",
    MAGMAW / "BotMagmawTransferLaneKernelBridge.cpp",
    MAGMAW / "BotMagmawTransferLaneIntent.cpp",
    MAGMAW / "BotMagmawTransferLaneAuthority.cpp",
    BOTS / "BotWorldPopulationMgrMovementExecution.cpp",
    BOTS / "BotWorldPopulationMgrMovementPlannerDiagnostics.cpp",
    BOTS / "BotWorldPopulationMgrMovementPlannerDiagnosticsJson.cpp",
    BOTS / "BotWorldPopulationMgrMovementReceiptRetention.cpp",
    BOTS / "BotWorldPopulationMgrMovementProgressDiagnostics.cpp",
]

PROBE = r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotAdaptiveMagmawStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawFacts.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawMovementKernelAdapter.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawPersonalParasiteEscapeDiagnostics.h"

#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

using namespace BotEncounter;
using TaskState = BotDecision::PersistentTaskState;
using Move = BotNativeAction::Move;

std::string ObjectGuid::ToString() const
{
    return std::to_string(GetRawValue());
}

#define CHECK(expr) do { if (!(expr)) { std::fprintf(stderr, \
    "CHECK failed line %d: %s\n", __LINE__, #expr); return 1; } } while (0)

static Vector3 const Support{ -308.909851f, -36.4524231f, 211.815f };
static Vector3 const MangledTank{ -290.2f, -40.4f, 211.1f };

static ObjectGuid PlayerGuid(uint32 counter)
{
    return ObjectGuid(HighGuid::Player, counter);
}

static ActorSnapshot Player(uint32 counter, char const* role,
    char const* spec, Vector3 position)
{
    ActorSnapshot actor;
    actor.Guid = PlayerGuid(counter);
    actor.Kind = ActorKind::Player;
    actor.Role = role;
    actor.ClassSpec = spec;
    actor.Position = position;
    actor.Alive = true;
    actor.HealthPct = 100.0f;
    return actor;
}

static ActorSnapshot Unit(uint32 entry, uint32 counter, Vector3 position)
{
    ActorSnapshot actor;
    actor.Guid = ObjectGuid(HighGuid::Unit, entry, counter);
    actor.Entry = entry;
    actor.Position = position;
    actor.Alive = true;
    actor.Attackable = true;
    actor.Selectable = true;
    return actor;
}

static Blackboard Board()
{
    Blackboard board;
    board.CurrentScope = { "platform-strand", 7, 0, 4,
        "bwd.magmaw.encounter", 669, 1, "magmaw", 91, 4 };
    board.Revision = 10;
    board.ObservedAtMs = 100000;
    board.NativeBossState = "in_progress";
    board.NativeWipeState = "engaged";
    board.EncounterIdentityAuthoritative = true;
    board.EncounterEpochAuthoritative = true;
    board.EncounterArenaObservationComplete = true;
    board.Route.NodeId = "bwd.magmaw.encounter";
    board.Route.NavigationHints = { { -307.531f, -35.4375f, 211.815f } };
    NativeEncounterLifecycle native;
    native.Id = "blackwing_descent.magmaw";
    native.BossId = 0;
    native.BossEntry = 41570;
    native.BossGuid = ObjectGuid(HighGuid::Unit, uint32(41570), uint32(1));
    native.State = NativeEncounterState::InProgress;
    native.ServerEpoch = 91;
    native.InstanceLifecycleEpoch = 3;
    native.AttemptEpoch = 4;
    native.EncounterEpoch = 4;
    native.Authoritative = true;
    board.NativeEncounter = native;
    board.Players = {
        Player(30002, "tank", "blood_death_knight", MangledTank),
        Player(30006, "dps", "fire_mage", { -337.3f, -35.0f, 211.5f }),
        Player(30009, "dps", "marksmanship_hunter", { -316.0f, -64.0f, 212.9f }),
        Player(30005, "healer", "discipline_priest", { -309.9f, -27.8f, 210.4f }),
        Player(30003, "healer", "restoration_druid", { -308.9f, -36.5f, 211.6f }),
        Player(30008, "dps", "affliction_warlock", { -314.4f, -20.5f, 211.1f }),
        Player(30010, "dps", "elemental_shaman", { -311.8f, -33.5f, 211.5f }),
        Player(30007, "dps", "arcane_mage", { -305.0f, -39.0f, 211.9f }) };
    ActorSnapshot boss = Unit(41570, 1, { -302.467f, -31.7101f, 210.8483f });
    boss.InCombat = true;
    boss.VictimGuid = PlayerGuid(30002);
    board.Hostiles = { boss };
    return board;
}

static ActorSnapshot* Find(Blackboard& board, uint32 counter)
{
    for (ActorSnapshot& actor : board.Players)
        if (actor.Guid == PlayerGuid(counter))
            return &actor;
    return nullptr;
}

// Native geometry of the incident corner, as observed offline on the 669
// tiles: the pit lip north of x=-313 (VMAP floor 208.9, no polygon) and the
// ledge north of x<=-313 (nearest polygon 10 yd up).
struct IncidentPlatform
{
    std::vector<Vector3> Probed;
    bool RejectAll = false;
    bool RejectSupport = false;
    bool LineOfSight = true;

    MagmawPlatformDestinationObservation Observe(Vector3 const& c,
        std::optional<Vector3> const& anchor)
    {
        Probed.push_back(c);
        MagmawPlatformDestinationObservation o;
        o.Observed = true;
        if (RejectAll)
            return o;
        o.FloorAvailable = true;
        bool const northOfEdge = c.Y > -22.0f;
        if (northOfEdge && c.X > -313.0f)
        {
            o.FloorZ = 208.9f;
            o.EndpointZ = 211.27f;
            return o;
        }
        o.FloorZ = 211.4f;
        o.OutboundComplete = true;
        if (northOfEdge)
        {
            o.EndpointZ = 222.0f;
            return o;
        }
        if (RejectSupport && std::hypot(c.X - Support.X, c.Y - Support.Y) < 1.0f)
        {
            o.EndpointZ = 222.0f;
            return o;
        }
        o.OutboundLevel = true;
        o.EndpointZ = 211.5f;
        if (anchor)
        {
            o.ReturnChecked = true;
            o.ReturnComplete = true;
            o.ReturnLevel = true;
        }
        return o;
    }

    MagmawNativeMovementProbe Probe()
    {
        MagmawNativeMovementProbe probe;
        probe.ObserveDestination = [this](Vector3 const& c,
            std::optional<Vector3> const& anchor) { return Observe(c, anchor); };
        probe.LineOfSightTo = [this](ObjectGuid) { return LineOfSight; };
        return probe;
    }
};

static BotNativeAction::Candidate const* MovementFor(
    AdaptiveMagmawPlan const& plan, char const* mechanic)
{
    for (BotNativeAction::Candidate const& candidate : plan.Movement.Proposals())
        if (candidate.Id.Mechanic == mechanic)
            return &candidate;
    return nullptr;
}

static Move const* MoveOf(BotNativeAction::Candidate const* candidate)
{
    return candidate ? std::get_if<Move>(&candidate->Action) : nullptr;
}

static float Distance2d(Vector3 const& left, float x, float y)
{
    return std::hypot(left.X - x, left.Y - y);
}

// Same feed as BotWorldPopulationMgrUpdateBotKernelCandidates.cpp.
static void ExecuteFormation(BotNativeAction::Candidate const& candidate,
    uint64 now, MagmawPersonalParasiteEscapeTask& task,
    BotActionArbitration::Outcome result)
{
    MagmawMovementIntentCollection movements;
    movements.Propose(MagmawMovementProposalOrigin::FormationRestore,
        candidate);
    MagmawMovementKernelAdapterContext context;
    context.ObservedAtMs = now;
    context.Execute = [result](BotNativeAction::Intent const&,
        MagmawMovementNativeLease, BotWorldMovement::ExecutionObservation*)
    {
        return result;
    };
    context.ObserveNativeOutcome = [&task](
        MagmawMovementNativeOutcome const& outcome)
    {
        if (outcome.Mechanic == "ranged_formation_restore")
            task.ReturnRecovery.ObserveReturnOutcome(outcome.Destination,
                outcome.Result.Result, outcome.Result.Reason,
                outcome.ObservedAtMs);
    };
    BotActionArbitration::Kernel kernel;
    kernel.Begin(now);
    SubmitMagmawMovementKernelCandidates(kernel, movements, std::move(context));
    kernel.Resolve();
}

static int VerdictContract()
{
    MagmawPlatformDestinationObservation lip;
    lip.Observed = true;
    lip.FloorAvailable = true;
    lip.FloorZ = 208.9f;
    CHECK(JudgeMagmawPlatformDestination(lip, Support.Z)
        == MagmawPlatformVerdict::BelowPlatform);
    MagmawPlatformDestinationObservation dip = lip;
    dip.FloorZ = 210.22f;
    dip.OutboundComplete = true;
    dip.OutboundLevel = true;
    dip.EndpointZ = 210.3f;
    dip.ReturnChecked = true;
    dip.ReturnComplete = true;
    dip.ReturnLevel = true;
    CHECK(JudgeMagmawPlatformDestination(dip, Support.Z)
        == MagmawPlatformVerdict::Admitted);
    MagmawPlatformDestinationObservation ledge = dip;
    ledge.OutboundLevel = false;
    CHECK(JudgeMagmawPlatformDestination(ledge, Support.Z)
        == MagmawPlatformVerdict::OutboundLevelGap);
    MagmawPlatformDestinationObservation noWayBack = dip;
    noWayBack.ReturnComplete = false;
    CHECK(JudgeMagmawPlatformDestination(noWayBack, Support.Z)
        == MagmawPlatformVerdict::ReturnIncomplete);
    MagmawPlatformDestinationObservation offMesh = dip;
    offMesh.OutboundComplete = false;
    CHECK(JudgeMagmawPlatformDestination(offMesh, Support.Z)
        == MagmawPlatformVerdict::OutboundIncomplete);
    CHECK(JudgeMagmawPlatformDestination({}, Support.Z)
        == MagmawPlatformVerdict::Unobserved);

    // The return anchor is the strategy's own support anchor.
    Blackboard board = Board();
    std::optional<Vector3> const anchor = ResolveMagmawSupportReturnAnchor(board);
    CHECK(anchor);
    CHECK(Distance2d(*anchor, Support.X, Support.Y) < 0.01f);
    CHECK(anchor->Z == Support.Z);
    ActorSnapshot* druid = Find(board, 30003);
    druid->Position = { -320.0f, -30.0f, 211.5f };
    AdaptiveMagmawStrategy strategy;
    AdaptiveMagmawPlan plan = strategy.Propose(board, druid->Guid, "healer");
    Move const* restore = MoveOf(MovementFor(plan, "ranged_formation_restore"));
    CHECK(restore);
    CHECK(Distance2d(*anchor, restore->X, restore->Y) < 0.01f);
    CHECK(restore->Z == anchor->Z);
    return 0;
}

// (a) An escape leg that would land on the pit lip below the platform is
// rejected natively and the next rotated candidate on the platform is used.
static int EscapeBelowPlatformRejected()
{
    Blackboard board = Board();
    ActorSnapshot parasite = Unit(41806, 190, { -310.4f, -40.2f, 211.7f });
    parasite.VictimGuid = PlayerGuid(30005);
    board.Hostiles.push_back(parasite);
    ActorSnapshot const& priest = *Find(board, 30005);
    AdaptiveMagmawStrategy strategy;
    MagmawParasiteWaveTask wave;
    auto cache = MagmawFactsCache::ForSnapshot(nullptr, board);

    // Legacy (no native probe): the unvalidated radial leg crosses the edge.
    {
        MagmawPersonalParasiteEscapeTask legacy;
        MagmawParasiteWaveTask legacyWave;
        AdaptiveMagmawPlan plan = strategy.Propose(board, priest.Guid,
            "healer", nullptr, false, false, nullptr, nullptr, nullptr,
            std::nullopt, AdaptiveMagmawStrategy::DefaultMovementProducerOrder,
            &cache->Facts(), &legacy, &legacyWave);
        Move const* radial = MoveOf(MovementFor(plan, "parasite_contact_evade"));
        CHECK(radial);
        CHECK(radial->Y > -22.0f);
        CHECK(radial->Z == priest.Position.Z);
    }

    IncidentPlatform platform;
    MagmawNativeMovementProbe const probe = platform.Probe();
    MagmawPersonalParasiteEscapeTask task;
    task.NativeProbe = &probe;
    AdaptiveMagmawPlan plan = strategy.Propose(board, priest.Guid, "healer",
        nullptr, false, false, nullptr, nullptr, nullptr, std::nullopt,
        AdaptiveMagmawStrategy::DefaultMovementProducerOrder,
        &cache->Facts(), &task, &wave);
    Move const* escape = MoveOf(MovementFor(plan, "parasite_contact_evade"));
    CHECK(escape);
    CHECK(platform.Probed.size() >= 2);
    Vector3 const radial = MagmawMoveAwayDestination(priest.Position,
        priest.Facing, parasite.Position, 20.0f);
    CHECK(Distance2d(platform.Probed.front(), radial.X, radial.Y) < 0.01f);
    CHECK(radial.Y > -22.0f);
    CHECK(escape->Y <= -22.0f);
    CHECK(escape->Z == 211.5f);
    CHECK(std::fabs(Distance2d(parasite.Position, escape->X, escape->Y)
        - 20.0f) < 0.05f);
    CHECK(task.State == TaskState::Running);
    CHECK(task.Platform.Rejected >= 1);
    CHECK(task.Platform.LastRejection == "below_platform");
    CHECK(task.Destination.Z == 211.5f);
    std::string const json = BuildMagmawPersonalParasiteEscapeDiagnosticsJson(task);
    CHECK(json.find("\"platform\":{\"probed\":") != std::string::npos);
    CHECK(json.find("\"last_rejection\":\"below_platform\"") != std::string::npos);
    task.NativeProbe = nullptr;

    // The ledge side: an actor already in the north-west corner gets no leg
    // onto the ledge (outbound level gap) and no leg over the lip.
    Blackboard corner = Board();
    ActorSnapshot pursuer = Unit(41806, 191, { -314.0f, -34.0f, 211.4f });
    pursuer.VictimGuid = PlayerGuid(30008);
    corner.Hostiles.push_back(pursuer);
    auto cornerCache = MagmawFactsCache::ForSnapshot(nullptr, corner);
    IncidentPlatform cornerPlatform;
    MagmawNativeMovementProbe const cornerProbe = cornerPlatform.Probe();
    MagmawPersonalParasiteEscapeTask lock;
    MagmawParasiteWaveTask lockWave;
    lock.NativeProbe = &cornerProbe;
    AdaptiveMagmawPlan lockPlan = strategy.Propose(corner, PlayerGuid(30008),
        "dps", nullptr, false, false, nullptr, nullptr, nullptr, std::nullopt,
        AdaptiveMagmawStrategy::DefaultMovementProducerOrder,
        &cornerCache->Facts(), &lock, &lockWave);
    Move const* lockEscape = MoveOf(MovementFor(lockPlan, "parasite_contact_evade"));
    CHECK(lockEscape);
    CHECK(lockEscape->Y <= -22.0f);
    CHECK(lock.Platform.LastRejection == "outbound_level_gap"
        || lock.Platform.LastRejection == "below_platform");
    return 0;
}

// (a) With no admitted candidate the actor holds position (no move, task
// still running) and re-samples only after the native retry interval.
static int EscapeHoldsWhenNothingAdmitted()
{
    Blackboard board = Board();
    ActorSnapshot parasite = Unit(41806, 190, { -310.4f, -40.2f, 211.7f });
    parasite.VictimGuid = PlayerGuid(30005);
    board.Hostiles.push_back(parasite);
    AdaptiveMagmawStrategy strategy;
    MagmawParasiteWaveTask wave;
    auto cache = MagmawFactsCache::ForSnapshot(nullptr, board);
    IncidentPlatform platform;
    platform.RejectAll = true;
    MagmawNativeMovementProbe const probe = platform.Probe();
    MagmawPersonalParasiteEscapeTask task;
    task.NativeProbe = &probe;
    auto tick = [&]()
    {
        cache = MagmawFactsCache::ForSnapshot(cache, board);
        return strategy.Propose(board, PlayerGuid(30005), "healer", nullptr,
            false, false, nullptr, nullptr, nullptr, std::nullopt,
            AdaptiveMagmawStrategy::DefaultMovementProducerOrder,
            &cache->Facts(), &task, &wave);
    };
    AdaptiveMagmawPlan plan = tick();
    CHECK(!MovementFor(plan, "parasite_contact_evade"));
    CHECK(platform.Probed.size() == 7);
    CHECK(task.Platform.Holds == 1);
    CHECK(task.Platform.LastRejection == "no_floor");
    CHECK(task.State == TaskState::Running);
    CHECK(task.CandidateGeneration == 0);

    board.Revision += 1;
    board.ObservedAtMs += 200;
    plan = tick();
    CHECK(!MovementFor(plan, "parasite_contact_evade"));
    CHECK(platform.Probed.size() == 7);

    board.Revision += 1;
    board.ObservedAtMs += MagmawPlatformNavigation::HoldRetryMs;
    platform.RejectAll = false;
    plan = tick();
    CHECK(MovementFor(plan, "parasite_contact_evade"));
    CHECK(task.State == TaskState::Running);
    CHECK(task.Failure == MagmawPersonalParasiteEscapeFailure::None);
    return 0;
}

// (b) Three consecutive native rejections of the same return destination
// switch the formation return to the nearest reachable group position.
static int RepeatedReturnFailureFallsBack()
{
    Blackboard board = Board();
    Find(board, 30005)->Position = { -306.5f, -38.5f, 211.8f };
    ActorSnapshot const& warlock = *Find(board, 30008);
    AdaptiveMagmawStrategy strategy;
    IncidentPlatform platform;
    platform.RejectSupport = true;
    MagmawNativeMovementProbe const probe = platform.Probe();
    MagmawPersonalParasiteEscapeTask task;
    task.NativeProbe = &probe;
    auto restore = [&]()
    {
        AdaptiveMagmawPlan plan = strategy.Propose(board, warlock.Guid, "dps",
            nullptr, false, false, nullptr, nullptr, nullptr, std::nullopt,
            AdaptiveMagmawStrategy::DefaultMovementProducerOrder, nullptr,
            &task);
        BotNativeAction::Candidate const* candidate =
            MovementFor(plan, "ranged_formation_restore");
        return candidate ? std::optional<BotNativeAction::Candidate>(*candidate)
            : std::nullopt;
    };
    auto const levelGap = BotActionArbitration::Outcome::Retryable(
        "route_destination_path_control_level_gap");
    for (uint32 attempt = 0; attempt < 2; ++attempt)
    {
        std::optional<BotNativeAction::Candidate> original = restore();
        CHECK(original);
        CHECK(Distance2d(Support, MoveOf(&*original)->X, MoveOf(&*original)->Y) < 0.01f);
        ExecuteFormation(*original, board.ObservedAtMs, task, levelGap);
        board.Revision += 1;
        board.ObservedAtMs += 1200;
    }
    // Two rejections are still an ordinary retry of the same destination.
    CHECK(task.ReturnRecovery.ConsecutiveFailures == 2);
    std::optional<BotNativeAction::Candidate> third = restore();
    CHECK(third);
    CHECK(Distance2d(Support, MoveOf(&*third)->X, MoveOf(&*third)->Y) < 0.01f);
    CHECK(platform.Probed.empty());
    ExecuteFormation(*third, board.ObservedAtMs, task, levelGap);
    CHECK(task.ReturnRecovery.ConsecutiveFailures == 3);
    CHECK(task.ReturnRecovery.LastReason
        == "route_destination_path_control_level_gap");

    board.Revision += 1;
    board.ObservedAtMs += 300;
    std::optional<BotNativeAction::Candidate> fallback = restore();
    CHECK(fallback);
    Move const* fallbackMove = MoveOf(&*fallback);
    // The shaman (-311.8, -33.5) is the nearest reachable ranged group
    // position; the support anchor itself is the failing destination.
    CHECK(Distance2d(Find(board, 30010)->Position, fallbackMove->X,
        fallbackMove->Y) < 0.01f);
    CHECK(fallbackMove->Z == 211.5f);
    CHECK(fallback->ActionPriority == BotActionArbitration::Priority::Mechanic);
    CHECK(task.ReturnRecovery.FallbackActive);
    CHECK(task.ReturnRecovery.FallbackCount == 1);
    ExecuteFormation(*fallback, board.ObservedAtMs, task,
        BotActionArbitration::Outcome::Submitted("native_move_submitted"));
    CHECK(task.ReturnRecovery.ConsecutiveFailures == 3);

    // Arrived at the reachable position: hold there, no retry spam.
    Find(board, 30008)->Position = { fallbackMove->X, fallbackMove->Y, 211.5f };
    board.Revision += 1;
    board.ObservedAtMs += 2000;
    CHECK(!restore());

    // After the strand hold the original destination is retried once, and a
    // committed return closes the strand.
    board.Revision += 1;
    board.ObservedAtMs += MagmawPlatformNavigation::StrandHoldMs;
    std::optional<BotNativeAction::Candidate> retry = restore();
    CHECK(retry);
    CHECK(Distance2d(Support, MoveOf(&*retry)->X, MoveOf(&*retry)->Y) < 0.01f);
    ExecuteFormation(*retry, board.ObservedAtMs, task,
        BotActionArbitration::Outcome::Submitted("native_move_submitted"));
    CHECK(task.ReturnRecovery.ConsecutiveFailures == 0);
    CHECK(!task.ReturnRecovery.FallbackActive);
    CHECK(task.ReturnRecovery.FallbackCount == 1);
    return 0;
}

// (b) With no reachable fallback the actor holds instead of retrying the
// failing destination every tick.
static int StrandWithoutReachableFallbackHolds()
{
    Blackboard board = Board();
    ActorSnapshot const& warlock = *Find(board, 30008);
    AdaptiveMagmawStrategy strategy;
    IncidentPlatform platform;
    platform.RejectAll = true;
    MagmawNativeMovementProbe const probe = platform.Probe();
    MagmawPersonalParasiteEscapeTask task;
    task.NativeProbe = &probe;
    auto restore = [&]()
    {
        AdaptiveMagmawPlan plan = strategy.Propose(board, warlock.Guid, "dps",
            nullptr, false, false, nullptr, nullptr, nullptr, std::nullopt,
            AdaptiveMagmawStrategy::DefaultMovementProducerOrder, nullptr,
            &task);
        return MovementFor(plan, "ranged_formation_restore") != nullptr;
    };
    // The first proposal binds the task to this scope (a scope change
    // resets the strand state) and still targets the support anchor.
    CHECK(restore());
    for (uint32 attempt = 0; attempt < 3; ++attempt)
        task.ReturnRecovery.ObserveReturnOutcome(Support,
            BotActionArbitration::Disposition::Retryable,
            "route_destination_path_control_level_gap", board.ObservedAtMs);
    // A neutral outcome (native lock) neither counts nor clears.
    task.ReturnRecovery.ObserveReturnOutcome(Support,
        BotActionArbitration::Disposition::Retryable, "global_cooldown",
        board.ObservedAtMs);
    CHECK(task.ReturnRecovery.ConsecutiveFailures == 3);
    CHECK(!restore());
    CHECK(task.ReturnRecovery.HoldCount == 1);
    size_t const probed = platform.Probed.size();
    CHECK(probed >= 1);
    board.ObservedAtMs += 100;
    CHECK(!restore());
    CHECK(platform.Probed.size() == probed);
    board.ObservedAtMs += MagmawPlatformNavigation::HoldRetryMs;
    CHECK(!restore());
    CHECK(platform.Probed.size() > probed);
    // Without a native probe (pure replay) the strand still holds.
    task.NativeProbe = nullptr;
    CHECK(!restore());
    return 0;
}

static AdaptiveMagmawPlan MangleFor(Blackboard const& board, uint32 counter,
    char const* role, IncidentPlatform* platform)
{
    static MagmawNativeMovementProbe probe;
    MagmawPersonalParasiteEscapeTask task;
    if (platform)
    {
        probe = platform->Probe();
        task.NativeProbe = &probe;
    }
    AdaptiveMagmawStrategy strategy;
    return strategy.Propose(board, PlayerGuid(counter), role, nullptr, false,
        false, nullptr, nullptr, nullptr, std::nullopt,
        AdaptiveMagmawStrategy::DefaultMovementProducerOrder, nullptr, &task);
}

// (c) HEAL-002: during Mangle a healer within 35 yd and in line of sight of
// the Mangled tank stays and heals; out of range or sight it still stages.
static int MangleHealerStaysInRange()
{
    Blackboard board = Board();
    Find(board, 30002)->Auras = { AuraSnapshot{ 89773u,
        board.Hostiles.front().Guid, 1, 0 } };
    ActorSnapshot* priest = Find(board, 30005);
    priest->Position = { -320.0f, -30.0f, 211.5f };
    CHECK(MagmawMangleSupportGeometry::WithinDistance(priest->Position,
        MangledTank, AdaptiveMagmawStrategy::MangleSupportMaxDistance));
    CHECK(Distance2d(Support, priest->Position.X, priest->Position.Y) > 4.0f);

    // Pre-fix behaviour (no native view): the stage move re-triggers.
    AdaptiveMagmawPlan legacy = MangleFor(board, 30005, "healer", nullptr);
    CHECK(MovementFor(legacy, "mangle_midpoint_stage"));

    IncidentPlatform visible;
    AdaptiveMagmawPlan stays = MangleFor(board, 30005, "healer", &visible);
    CHECK(!MovementFor(stays, "mangle_midpoint_stage"));
    CHECK(stays.Movement.Empty());
    CHECK(stays.PriorityHealTarget == PlayerGuid(30002));

    IncidentPlatform blocked;
    blocked.LineOfSight = false;
    AdaptiveMagmawPlan noSight = MangleFor(board, 30005, "healer", &blocked);
    Move const* stage = MoveOf(MovementFor(noSight, "mangle_midpoint_stage"));
    CHECK(stage);
    CHECK(Distance2d(Support, stage->X, stage->Y) < 0.01f);
    CHECK(noSight.PriorityHealTarget == PlayerGuid(30002));

    Blackboard far = board;
    Find(far, 30005)->Position = { -330.0f, -35.0f, 211.5f };
    CHECK(!MagmawMangleSupportGeometry::WithinDistance(
        Find(far, 30005)->Position, MangledTank,
        AdaptiveMagmawStrategy::MangleSupportMaxDistance));
    IncidentPlatform farVisible;
    CHECK(MovementFor(MangleFor(far, 30005, "healer", &farVisible),
        "mangle_midpoint_stage"));

    // The rule is the healer's: an in-range DPS still stages.
    Blackboard dps = board;
    Find(dps, 30010)->Position = { -320.0f, -30.0f, 211.5f };
    IncidentPlatform dpsVisible;
    CHECK(MovementFor(MangleFor(dps, 30010, "dps", &dpsVisible),
        "mangle_midpoint_stage"));

    // Hazard avoidance is untouched: a pillar under the in-range healer
    // still moves it.
    Blackboard pillar = board;
    pillar.Summons.push_back(Unit(41843, 300, { -320.5f, -30.5f, 211.5f }));
    IncidentPlatform pillarVisible;
    CHECK(MovementFor(MangleFor(pillar, 30005, "healer", &pillarVisible),
        "pillar_evade"));

    // A stage point that is not admitted on the platform is not issued.
    IncidentPlatform nothing;
    nothing.RejectAll = true;
    nothing.LineOfSight = false;
    CHECK(!MovementFor(MangleFor(board, 30005, "healer", &nothing),
        "mangle_midpoint_stage"));
    return 0;
}

int main()
{
    if (int const failed = VerdictContract())
        return failed;
    if (int const failed = EscapeBelowPlatformRejected())
        return failed;
    if (int const failed = EscapeHoldsWhenNothingAdmitted())
        return failed;
    if (int const failed = RepeatedReturnFailureFallsBack())
        return failed;
    if (int const failed = StrandWithoutReachableFallbackHolds())
        return failed;
    return MangleHealerStaysInRange();
}
'''


def _compile(tmp_path: Path) -> Path:
    source = tmp_path / "magmaw_platform_strand_recovery.cpp"
    binary = tmp_path / "magmaw_platform_strand_recovery"
    source.write_text(PROBE, encoding="utf-8")
    result = subprocess.run(
        ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", *INCLUDES,
         str(source), *(str(path) for path in SOURCES), "-o", str(binary)],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr[-6000:]
    return binary


def test_platform_destination_escape_strand_and_mangle_replays(tmp_path: Path) -> None:
    binary = _compile(tmp_path)
    result = subprocess.run([str(binary)], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_native_probe_reads_terrain_without_steering_or_loosening() -> None:
    probe = (MAGMAW / "BotMagmawPlatformNativeProbe.h").read_text(encoding="utf-8")
    value = (MAGMAW / "BotMagmawPlatformDestination.h").read_text(encoding="utf-8")
    task = (MAGMAW / "BotMagmawPersonalParasiteEscapeTask.inl").read_text(encoding="utf-8")
    for required in ("NativePathIsComplete", "NativePathEndpointMatches",
                     "NativePathControlsMatchReferenceLevel", "IsWithinLOSInMap",
                     "GetHeight("):
        assert required in probe
    for forbidden in ("Relocate", "NearTeleportTo", "MotionMaster", "MovePoint",
                      "NativeFloorTolerance =", "NativePathPointFloorTolerance =",
                      "UpdateAllowedPositionZ"):
        assert forbidden not in probe
        assert forbidden not in value
    assert "PathGenerator" not in value
    assert "PathGenerator" not in task
    assert ".Z +=" not in value and ".Z -=" not in value


def test_world_layer_scopes_the_probe_and_feeds_return_outcomes() -> None:
    preparation = (BOTS / "BotWorldPopulationMgrUpdateBotKernelPreparation.cpp").read_text(
        encoding="utf-8")
    candidates = (BOTS / "BotWorldPopulationMgrUpdateBotKernelCandidates.cpp").read_text(
        encoding="utf-8")
    set_at = preparation.index("MagmawPersonalParasiteEscape.NativeProbe =\n")
    propose_at = preparation.index("magmawStrategy.Propose(", set_at)
    clear_at = preparation.index("MagmawPersonalParasiteEscape.NativeProbe = nullptr;")
    assert set_at < propose_at < clear_at
    feed = candidates.index('outcome.Mechanic == "ranged_formation_restore"')
    assert "ReturnRecovery" in candidates[feed:feed + 600]
