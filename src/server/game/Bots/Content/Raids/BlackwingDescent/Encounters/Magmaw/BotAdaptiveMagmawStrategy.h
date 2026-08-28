#ifndef TRINITY_BOT_ADAPTIVE_MAGMAW_STRATEGY_H
#define TRINITY_BOT_ADAPTIVE_MAGMAW_STRATEGY_H

#include "Bots/BotEncounterBlackboard.h"
#include "Bots/BotMovementArbiter.h"
#include "Bots/BotNativeActionIntent.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotAdaptiveMagmawParasitePolicy.h"
#include <algorithm>
#include <cmath>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace BotEncounter
{
struct AdaptiveMagmawPlan
{
    bool OwnsNode = false;
    bool SuppressOffense = false;
    ObjectGuid DamageTarget;
    std::optional<BotNativeAction::Candidate> Movement;
    std::optional<BotNativeAction::Candidate> Interaction;
};

class AdaptiveMagmawStrategy
{
public:
    static constexpr uint32 BossEntry = 41570;
    static constexpr uint32 HeadEntry = 42347;
    static constexpr uint32 PillarEntry = 41843;
    static constexpr uint32 ParasiteEntry = 41806;
    static constexpr uint32 ParasiteAltEntry = 42321;
    static constexpr uint32 CrashEntry = 47330;
    static constexpr uint32 RoomStalkerEntry = 47196;
    static constexpr uint32 PincerLeftEntry = 41620;
    static constexpr uint32 PincerRightEntry = 41789;
    static constexpr uint32 SpikeEntry = 41767;
    static constexpr float HookInteractionDistance = 5.0f;
    static constexpr float RangedStackDistance = 30.0f;
    static constexpr float SupportStackDistance = 22.0f;
    // The two bait endpoints must be outside the support stack while still
    // leaving a full left/right lane for the mobile team to cross.
    static constexpr float RangedStackLateralOffset = 24.0f;
    static constexpr float RangedStackTolerance = 4.0f;
    static constexpr float ParasiteKiteLeadDistance =
        MagmawParasitePolicy::KiteLeadDistance;
    static constexpr float RangedParasiteTargetDistance =
        RangedStackDistance + RangedStackLateralOffset +
        MagmawParasitePolicy::SafeClearance;

    AdaptiveMagmawPlan Propose(Blackboard const& board, ObjectGuid botGuid,
        std::string_view role,
        BotMovementArbitration::Lease const* movementLease = nullptr,
        bool activePathValid = false, bool moving = false) const
    {
        AdaptiveMagmawPlan plan;
        if (board.Route.NodeId != "bwd.magmaw.encounter")
            return plan;
        ActorSnapshot const* bot = board.FindActor(botGuid);
        if (!bot || !bot->Alive)
            return plan;

        MagmawActorObservation const observed = ObserveMagmawActors(board, *bot);
        if (!observed.Boss)
            return plan;

        plan.OwnsNode = true;
        PrepullDecision prepull = EvaluatePrepull(board, *observed.Boss);
        if (IsPrepull(board, *observed.Boss))
        {
            std::optional<MagmawRangedAnchors> const anchors =
                ResolveRangedAnchors(board, *observed.Boss);
            if (anchors && !RangedGroupStaged(board, *anchors))
            {
                plan.SuppressOffense = true;
                if (role != "tank")
                    plan.Movement = BuildPointMovement(board, *bot,
                        FormationAnchor(board, *anchors, botGuid),
                        "prepull_ranged_stage",
                        BotActionArbitration::Priority::Mechanic, 325.0f);
                return plan;
            }
            if (prepull.Disposition == PrepullDisposition::HoldOffense)
            {
                plan.SuppressOffense = true;
                return plan;
            }
            if (!IsDesignatedPullTank(board, botGuid, role))
            {
                plan.SuppressOffense = true;
                return plan;
            }
        }

        plan.DamageTarget = SelectDamageTarget(board, observed, botGuid, role);
        MagmawHookAssignment const hookAssignment = ResolveHookAssignment(
            board, *bot, botGuid);
        bool const pincerWarning = PincerWarningObserved(board);
        bool const pincerWindow = PincerCommitmentActive(hookAssignment,
            *observed.Boss, pincerWarning);
        plan.Interaction = ProposeHookInteraction(board, *bot, *observed.Boss,
            botGuid);
        plan.Movement = ProposeHazardMovement(board, *bot, *observed.Boss,
            pincerWindow, pincerWarning, movementLease);
        if (!plan.Movement)
            plan.Movement = ProposeHookPreposition(board, *bot,
                *observed.Boss, botGuid);
        if (!plan.Movement)
            plan.Movement = ProposeHookApproach(board, *bot, *observed.Boss,
                botGuid);
        if (!plan.Movement && !pincerWindow
            && !(IsPillarBaiter(board, botGuid) && HasActivePillar(board))
            && !HasLivingParasite(board)
            && !HasActiveHazardPath(board, movementLease, activePathValid,
                moving))
            plan.Movement = ProposeRangedFormationRestore(board, *bot,
                *observed.Boss, role);
        return plan;
    }

private:
    struct MagmawActorObservation
    {
        ActorSnapshot const* Boss = nullptr;
        ActorSnapshot const* Head = nullptr;
        ActorSnapshot const* NearestParasite = nullptr;
        float NearestParasiteDistance = 0.0f;
    };

    enum class PrepullDisposition : uint8
    {
        NotApplicable,
        HoldOffense
    };

    struct PrepullDecision
    {
        PrepullDisposition Disposition = PrepullDisposition::NotApplicable;
    };

    struct MagmawHazardObservation
    {
        ActorSnapshot const* Pillar = nullptr;
        ActorSnapshot const* NearestImmediateHazard = nullptr;
        float NearestImmediateHazardDistance = 0.0f;
    };

    struct MagmawHookAssignment
    {
        bool Assigned = false;
        ActorSnapshot const* Vehicle = nullptr;
        ActorSnapshot const* Spike = nullptr;
    };

    using MagmawRangedAnchors = MagmawParasitePolicy::FormationAnchors;

    static bool IsParasiteEntry(uint32 entry)
    {
        return entry == ParasiteEntry || entry == ParasiteAltEntry;
    }

    static MagmawActorObservation ObserveMagmawActors(Blackboard const& board,
        ActorSnapshot const& bot)
    {
        MagmawActorObservation observed;
        auto inspectTarget = [&observed, &bot](ActorSnapshot const& actor)
        {
            if (!actor.Alive)
                return;
            if (actor.Entry == BossEntry)
                observed.Boss = &actor;
            else if (actor.Entry == HeadEntry && actor.Selectable
                && actor.Attackable)
                observed.Head = &actor;
            else if (IsParasiteEntry(actor.Entry))
            {
                float const distance = Distance2d(bot.Position, actor.Position);
                if (!observed.NearestParasite
                    || distance < observed.NearestParasiteDistance)
                {
                    observed.NearestParasite = &actor;
                    observed.NearestParasiteDistance = distance;
                }
            }
        };
        for (ActorSnapshot const& actor : board.Hostiles)
            inspectTarget(actor);
        for (ActorSnapshot const& actor : board.Summons)
            inspectTarget(actor);
        return observed;
    }

    static std::optional<size_t> PillarBaiterRank(
        Blackboard const& board, ObjectGuid botGuid)
    {
        std::vector<ActorSnapshot const*> dps;
        for (ActorSnapshot const& member : board.Players)
            if (member.Role == "dps")
                dps.push_back(&member);
        std::sort(dps.begin(), dps.end(), [](ActorSnapshot const* left,
            ActorSnapshot const* right)
        {
            return left->Guid.GetRawValue() < right->Guid.GetRawValue();
        });

        std::vector<ObjectGuid> baiters;
        for (std::string_view const spec : {
                std::string_view("marksmanship_hunter"),
                std::string_view("fire_mage") })
        {
            auto const preferred = std::find_if(dps.begin(), dps.end(),
                [spec](ActorSnapshot const* member)
                {
                    return member->ClassSpec == spec;
                });
            if (preferred == dps.end())
                return std::nullopt;
            baiters.push_back((*preferred)->Guid);
        }

        auto const baiter = std::find(baiters.begin(), baiters.end(), botGuid);
        if (baiter == baiters.end())
            return std::nullopt;
        return size_t(std::distance(baiters.begin(), baiter));
    }

    static bool IsPillarBaiter(Blackboard const& board, ObjectGuid botGuid)
    {
        return PillarBaiterRank(board, botGuid).has_value();
    }

    static bool IsDesignatedPullTank(Blackboard const& board,
        ObjectGuid botGuid, std::string_view role)
    {
        if (role != "tank")
            return false;
        ObjectGuid pullTank;
        for (ActorSnapshot const& member : board.Players)
            if (member.Alive && member.Role == "tank"
                && (pullTank.IsEmpty()
                    || member.Guid.GetRawValue() < pullTank.GetRawValue()))
                pullTank = member.Guid;
        return !pullTank.IsEmpty() && pullTank == botGuid;
    }

    static bool IsPrepull(Blackboard const& board, ActorSnapshot const& boss)
    {
        bool const bossEngaged = boss.InCombat || !boss.VictimGuid.IsEmpty();
        return !bossEngaged && board.NativeBossState != "in_progress";
    }

    static PrepullDecision EvaluatePrepull(Blackboard const& board,
        ActorSnapshot const& boss)
    {
        PrepullDecision decision;
        if (!IsPrepull(board, boss))
            return decision;

        bool const prepullHealthIncomplete = std::any_of(board.Players.begin(),
            board.Players.end(), [](ActorSnapshot const& member)
            {
                return !member.Alive || member.HealthPct < 94.0f;
            });
        if (prepullHealthIncomplete)
        {
            decision.Disposition = PrepullDisposition::HoldOffense;
            return decision;
        }
        // A tank may begin the pull from range.  Normal combat movement owns
        // melee closure after Magmaw is engaged; prepull suppression is only
        // for an injured cohort that still needs health recovery.
        return decision;
    }

    static ObjectGuid SelectDamageTarget(Blackboard const& board,
        MagmawActorObservation const& observed, ObjectGuid botGuid,
        std::string_view role)
    {
        if (observed.Head)
            return observed.Head->Guid;
        if (role == "dps" && IsPillarBaiter(board, botGuid)
            && observed.NearestParasite
            && observed.NearestParasiteDistance <= RangedParasiteTargetDistance)
            return observed.NearestParasite->Guid;
        return observed.Boss->Guid;
    }

    static bool Finite(Vector3 const& point)
    {
        return std::isfinite(point.X) && std::isfinite(point.Y)
            && std::isfinite(point.Z);
    }

    static std::optional<MagmawRangedAnchors> ResolveRangedAnchors(
        Blackboard const& board, ActorSnapshot const& boss)
    {
        if (board.Route.NavigationHints.empty()
            || !Finite(board.Route.NavigationHints.front())
            || !Finite(boss.Position))
            return std::nullopt;

        Vector3 const& roomSide = board.Route.NavigationHints.front();
        float dx = roomSide.X - boss.Position.X;
        float dy = roomSide.Y - boss.Position.Y;
        float const length = std::sqrt(dx * dx + dy * dy);
        if (length < 1.0f)
            return std::nullopt;
        dx /= length;
        dy /= length;
        float const centerX = boss.Position.X + dx * RangedStackDistance;
        float const centerY = boss.Position.Y + dy * RangedStackDistance;
        float const supportX = boss.Position.X + dx * SupportStackDistance;
        float const supportY = boss.Position.Y + dy * SupportStackDistance;
        float const lateralX = -dy * RangedStackLateralOffset;
        float const lateralY = dx * RangedStackLateralOffset;
        return MagmawRangedAnchors{
            { supportX, supportY, roomSide.Z },
            { centerX + lateralX, centerY + lateralY, roomSide.Z },
            { centerX - lateralX, centerY - lateralY, roomSide.Z } };
    }

    static Vector3 const& PrepullAnchor(Blackboard const& board,
        MagmawRangedAnchors const& anchors)
    {
        return board.CurrentScope.AttemptId % 2 ? anchors.Left : anchors.Right;
    }

    static Vector3 const& FormationAnchor(Blackboard const& board,
        MagmawRangedAnchors const& anchors, ObjectGuid const& botGuid)
    {
        return IsPillarBaiter(board, botGuid)
            ? PrepullAnchor(board, anchors) : anchors.Support;
    }

    static bool RangedGroupStaged(Blackboard const& board,
        MagmawRangedAnchors const& anchors)
    {
        return std::all_of(board.Players.begin(), board.Players.end(),
            [&board, &anchors](ActorSnapshot const& member)
            {
                Vector3 const& anchor = FormationAnchor(board, anchors,
                    member.Guid);
                return !member.Alive || member.Role == "tank"
                    || Distance2d(member.Position, anchor)
                        <= RangedStackTolerance;
            });
    }

    static std::optional<Vector3> ResolveHookApproachDestination(
        Blackboard const& board, ActorSnapshot const& bot,
        ActorSnapshot const& boss)
    {
        std::optional<MagmawRangedAnchors> const anchors =
            ResolveRangedAnchors(board, boss);
        if (!anchors)
            return std::nullopt;
        float dx = anchors->Left.X + anchors->Right.X
            - 2.0f * boss.Position.X;
        float dy = anchors->Left.Y + anchors->Right.Y
            - 2.0f * boss.Position.Y;
        float const length = std::sqrt(dx * dx + dy * dy);
        if (length < 0.01f)
            return std::nullopt;
        return Vector3{
            boss.Position.X + dx / length * 4.0f,
            boss.Position.Y + dy / length * 4.0f,
            bot.Position.Z };
    }

    static BotNativeAction::Candidate BuildPointMovement(
        Blackboard const& board, ActorSnapshot const& bot,
        Vector3 const& point, std::string mechanic,
        BotActionArbitration::Priority priority, float utility)
    {
        BotNativeAction::Candidate candidate;
        candidate.Id.ScopeKey = board.CurrentScope.Key();
        candidate.Id.Strategy = "adaptive_magmaw";
        candidate.Id.Mechanic = std::move(mechanic);
        candidate.Id.EventGeneration = board.Revision;
        candidate.ActionPriority = priority;
        candidate.Utility = utility;
        candidate.ExpiresAtMs = board.ObservedAtMs + 750;
        candidate.Action = BotNativeAction::Move{ point.X, point.Y,
            bot.Position.Z };
        return candidate;
    }

    static ActorSnapshot const* FindFirstAliveActorByEntry(
        std::vector<ActorSnapshot> const& actors, uint32 entry)
    {
        auto itr = std::find_if(actors.begin(), actors.end(), [entry](
            ActorSnapshot const& actor)
        {
            return actor.Alive && actor.Entry == entry;
        });
        return itr == actors.end() ? nullptr : &*itr;
    }

    static bool IsImmediateHazard(ActorSnapshot const& actor)
    {
        bool const litCrash = actor.Entry == RoomStalkerEntry
            && HasAura(actor, 87949);
        bool const parasite = IsParasiteEntry(actor.Entry);
        return actor.Alive && (litCrash || parasite);
    }

    static MagmawHazardObservation ObserveHazards(Blackboard const& board,
        ActorSnapshot const& bot)
    {
        MagmawHazardObservation observed;
        for (ActorSnapshot const& actor : board.Summons)
            if (actor.Alive && actor.Entry == PillarEntry
                && (!observed.Pillar
                    || Distance2d(bot.Position, actor.Position)
                        < Distance2d(bot.Position, observed.Pillar->Position)))
                observed.Pillar = &actor;
        auto inspectHazard = [&observed, &bot](ActorSnapshot const& actor)
        {
            if (!IsImmediateHazard(actor))
                return;
            float const distance = Distance2d(bot.Position, actor.Position);
            if (!observed.NearestImmediateHazard
                || distance < observed.NearestImmediateHazardDistance)
            {
                observed.NearestImmediateHazard = &actor;
                observed.NearestImmediateHazardDistance = distance;
            }
        };
        for (ActorSnapshot const& actor : board.Hostiles)
            inspectHazard(actor);
        for (ActorSnapshot const& actor : board.Summons)
            inspectHazard(actor);
        return observed;
    }

    static std::optional<BotNativeAction::Candidate> BuildPillarEvade(
        Blackboard const& board, ActorSnapshot const& bot,
        ActorSnapshot const& pillar)
    {
        float dx = bot.Position.X - pillar.Position.X;
        float dy = bot.Position.Y - pillar.Position.Y;
        float distance = std::sqrt(dx * dx + dy * dy);
        if (distance <= 12.0f)
        {
            if (distance < 0.01f)
            {
                dx = std::cos(bot.Facing);
                dy = std::sin(bot.Facing);
                distance = 1.0f;
            }
            BotNativeAction::Candidate candidate;
            candidate.Id.ScopeKey = board.CurrentScope.CohortId + ":"
                + std::to_string(board.CurrentScope.AttemptId) + ":"
                + std::to_string(board.CurrentScope.WipeGeneration) + ":"
                + std::to_string(board.CurrentScope.RouteGeneration) + ":"
                + board.CurrentScope.NodeId;
            candidate.Id.Strategy = "adaptive_magmaw";
            candidate.Id.Mechanic = "pillar_evade";
            candidate.Id.Actor = pillar.Guid;
            candidate.Id.EventGeneration = board.Revision;
            candidate.ActionPriority = BotActionArbitration::Priority::Survival;
            candidate.Utility = 500.0f - distance;
            candidate.ExpiresAtMs = board.ObservedAtMs + 750;
            candidate.Action = BotNativeAction::Move{
                pillar.Position.X + dx / distance * 15.0f,
                pillar.Position.Y + dy / distance * 15.0f,
                bot.Position.Z };
            return candidate;
        }
        return std::nullopt;
    }

    static std::optional<BotNativeAction::Candidate> BuildPillarBaitMove(
        Blackboard const& board, ActorSnapshot const& bot,
        ActorSnapshot const& boss, ActorSnapshot const& pillar,
        BotMovementArbitration::Lease const* movementLease)
    {
        if (!IsPillarBaiter(board, bot.Guid))
            return std::nullopt;
        std::optional<MagmawRangedAnchors> const anchors =
            ResolveRangedAnchors(board, boss);
        if (!anchors)
            return std::nullopt;
        std::optional<Vector3> destination =
            MagmawParasitePolicy::RetainedLaneDestination(
                board, *anchors, movementLease);
        if (destination
            && Distance2d(*destination, pillar.Position)
                < MagmawParasitePolicy::SafeClearance)
            destination.reset();
        if (!destination)
        {
            Vector3 const preferred =
                MagmawParasitePolicy::OppositeLaneEndpoint(
                    board, bot, *anchors);
            Vector3 const alternate = Distance2d(preferred, anchors->Left)
                    <= Distance2d(preferred, anchors->Right)
                ? anchors->Right : anchors->Left;
            destination = Distance2d(preferred, pillar.Position)
                    >= MagmawParasitePolicy::SafeClearance
                ? std::optional<Vector3>(preferred)
                : std::optional<Vector3>(alternate);
        }
        if (!destination
            || Distance2d(bot.Position, *destination)
                <= RangedStackTolerance)
            return std::nullopt;
        BotNativeAction::Candidate candidate = BuildPointMovement(
            board, bot, *destination, "pillar_bait_switch",
            BotActionArbitration::Priority::Survival, 500.0f);
        candidate.Id.Actor = pillar.Guid;
        candidate.Id.EventGeneration = pillar.Guid.GetRawValue();
        if (BotNativeAction::Move* move =
                std::get_if<BotNativeAction::Move>(&candidate.Action))
        {
            move->Z = destination->Z;
            move->IntentReason = "pillar_bait_switch";
        }
        return candidate;
    }

    static bool HasActivePillar(Blackboard const& board)
    {
        return std::any_of(board.Summons.begin(), board.Summons.end(),
            [](ActorSnapshot const& actor)
            {
                return actor.Alive && actor.Entry == PillarEntry;
            });
    }

    static bool HasLivingParasite(Blackboard const& board)
    {
        return MagmawParasitePolicy::HasLivingParasite(board);
    }

    static bool HasActiveHazardPath(Blackboard const& board,
        BotMovementArbitration::Lease const* movementLease,
        bool activePathValid, bool moving)
    {
        return MagmawParasitePolicy::HasActiveHazardPath(board,
            movementLease, activePathValid, moving);
    }

    static bool IsCrashHazard(ActorSnapshot const& actor)
    {
        return actor.Entry == RoomStalkerEntry && HasAura(actor, 87949);
    }

    static bool HasMangleAura(ActorSnapshot const& actor)
    {
        return HasAura(actor, 89773) || HasAura(actor, 78412);
    }

    static bool IsPincerWarningActor(ActorSnapshot const& actor)
    {
        // Persistent Massive Crash dummies are not a transient telegraph;
        // only the lit Room Stalker carries that native warning state.
        return actor.Alive && actor.Entry == RoomStalkerEntry
            && HasAura(actor, 87949);
    }

    static bool PincerWarningObserved(Blackboard const& board)
    {
        for (ActorSnapshot const& member : board.Players)
            if (member.Alive && HasMangleAura(member))
                return true;
        for (std::vector<ActorSnapshot> const* actors : {
                 &board.Hostiles, &board.Summons })
            for (ActorSnapshot const& actor : *actors)
                if (IsPincerWarningActor(actor))
                    return true;
        return false;
    }

    static bool PincerCommitmentActive(
        MagmawHookAssignment const& assignment, ActorSnapshot const& boss,
        bool warningObserved)
    {
        return assignment.Assigned && (boss.Interactable || warningObserved);
    }

    static std::optional<BotNativeAction::Candidate>
    ProposeImmediateCrashDuringPincer(Blackboard const& board,
        ActorSnapshot const& bot, ActorSnapshot const& boss,
        MagmawHazardObservation const& observed)
    {
        if (boss.Interactable || !observed.NearestImmediateHazard
            || observed.NearestImmediateHazardDistance > 12.0f
            || !IsCrashHazard(*observed.NearestImmediateHazard))
            return std::nullopt;
        return MoveAway(board, bot, *observed.NearestImmediateHazard,
            "massive_crash_evade", 16.0f);
    }

    static std::optional<BotNativeAction::Candidate> ProposeHazardMovement(
        Blackboard const& board, ActorSnapshot const& bot,
        ActorSnapshot const& boss, bool pincerWindow, bool pincerWarning,
        BotMovementArbitration::Lease const* movementLease)
    {
        MagmawHazardObservation const observed = ObserveHazards(board, bot);
        if (observed.Pillar)
        {
            if (pincerWindow)
            {
                if (std::optional<BotNativeAction::Candidate> const pillar =
                        BuildPillarEvade(board, bot, *observed.Pillar))
                    return pillar;
            }
            else
            {
                if (std::optional<BotNativeAction::Candidate> const bait =
                        BuildPillarBaitMove(board, bot, boss, *observed.Pillar,
                            movementLease))
                    return bait;
                if (std::optional<BotNativeAction::Candidate> const pillar =
                        BuildPillarEvade(board, bot, *observed.Pillar))
                    return pillar;
            }
        }

        if (pincerWindow)
        {
            if (std::optional<BotNativeAction::Candidate> const crash =
                    ProposeImmediateCrashDuringPincer(board, bot, boss,
                        observed))
                return crash;
            return std::nullopt;
        }

        bool const pillarBaiter = IsPillarBaiter(board, bot.Guid);
        if (pillarBaiter && observed.NearestImmediateHazard
            && IsParasiteEntry(observed.NearestImmediateHazard->Entry))
        {
            std::optional<MagmawParasitePolicy::FormationAnchors> anchors;
            if (std::optional<MagmawRangedAnchors> const rangedAnchors =
                    ResolveRangedAnchors(board, boss))
                anchors = *rangedAnchors;
            if (anchors)
                if (std::optional<BotNativeAction::Candidate> const lane =
                        MagmawParasitePolicy::Propose(board, bot,
                            *observed.NearestImmediateHazard, true, anchors,
                            movementLease))
                    return lane;
        }
        float const immediateDistance = observed.NearestImmediateHazard
                && IsParasiteEntry(observed.NearestImmediateHazard->Entry)
            ? MagmawParasitePolicy::ImmediateContactRange(pillarBaiter)
            : 12.0f;
        if (observed.NearestImmediateHazard
            && observed.NearestImmediateHazardDistance <= immediateDistance)
        {
            if (IsCrashHazard(*observed.NearestImmediateHazard))
                return MoveAway(board, bot,
                    *observed.NearestImmediateHazard,
                    "massive_crash_evade", 16.0f);
            std::optional<MagmawParasitePolicy::FormationAnchors> anchors;
            if (pillarBaiter)
                if (std::optional<MagmawRangedAnchors> const rangedAnchors =
                        ResolveRangedAnchors(board, boss))
                    anchors = *rangedAnchors;
            return MagmawParasitePolicy::Propose(board, bot,
                *observed.NearestImmediateHazard, pillarBaiter, anchors,
                movementLease);
        }

        if (pincerWarning && !HasMangleAura(bot))
            if (std::optional<MagmawRangedAnchors> const anchors =
                    ResolveRangedAnchors(board, boss))
            {
                Vector3 const& destination = observed.NearestImmediateHazard
                        && IsCrashHazard(*observed.NearestImmediateHazard)
                    ? (Distance2d(anchors->Left,
                            observed.NearestImmediateHazard->Position)
                            >= Distance2d(anchors->Right,
                                observed.NearestImmediateHazard->Position)
                        ? anchors->Left : anchors->Right)
                    : anchors->Support;
                if (Distance2d(bot.Position, destination)
                    > RangedStackTolerance)
                    return BuildPointMovement(board, bot, destination,
                        observed.NearestImmediateHazard
                            && IsCrashHazard(*observed.NearestImmediateHazard)
                            ? "mangle_safe_side" : "mangle_midpoint_stage",
                        BotActionArbitration::Priority::Survival, 490.0f);
            }
        return std::nullopt;
    }

    static std::optional<BotNativeAction::Candidate>
    ProposeRangedFormationRestore(Blackboard const& board,
        ActorSnapshot const& bot, ActorSnapshot const& boss,
        std::string_view role)
    {
        if (role == "tank")
            return std::nullopt;
        std::optional<MagmawRangedAnchors> const anchors =
            ResolveRangedAnchors(board, boss);
        if (!anchors)
            return std::nullopt;
        Vector3 const& destination = FormationAnchor(board, *anchors,
            bot.Guid);
        if (Distance2d(bot.Position, destination) <= RangedStackTolerance)
            return std::nullopt;
        return BuildPointMovement(board, bot, destination,
            "ranged_formation_restore",
            BotActionArbitration::Priority::Mechanic, 275.0f);
    }

    static std::vector<ObjectGuid> BuildHookUsers(Blackboard const& board)
    {
        std::vector<ObjectGuid> hookUsers;
        for (ActorSnapshot const& member : board.Players)
            if (member.Alive && member.Role == "dps")
                hookUsers.push_back(member.Guid);
        std::sort(hookUsers.begin(), hookUsers.end(), [](ObjectGuid left,
            ObjectGuid right)
        {
            return left.GetRawValue() < right.GetRawValue();
        });
        if (hookUsers.size() < 2)
            for (ActorSnapshot const& member : board.Players)
                if (member.Alive && member.Role != "tank"
                    && std::find(hookUsers.begin(), hookUsers.end(), member.Guid)
                        == hookUsers.end())
                    hookUsers.push_back(member.Guid);
        return hookUsers;
    }

    static bool IsAssignedHookUser(std::vector<ObjectGuid> const& hookUsers,
        ObjectGuid botGuid)
    {
        auto hookUser = std::find(hookUsers.begin(), hookUsers.end(), botGuid);
        return hookUser != hookUsers.end()
            && std::distance(hookUsers.begin(), hookUser) < 2;
    }

    static MagmawHookAssignment ResolveHookAssignment(
        Blackboard const& board, ActorSnapshot const& bot, ObjectGuid botGuid)
    {
        std::vector<ObjectGuid> const hookUsers = BuildHookUsers(board);
        if (!IsAssignedHookUser(hookUsers, botGuid))
            return {};
        return { true, board.FindActor(bot.VehicleGuid),
            FindActorByEntry(board, SpikeEntry) };
    }

    static bool IsPincerVehicle(ActorSnapshot const& vehicle)
    {
        return vehicle.Entry == PincerLeftEntry
            || vehicle.Entry == PincerRightEntry;
    }

    static BotNativeAction::Candidate BuildHookCandidate(Blackboard const& board,
        ActorSnapshot const& vehicle, ActorSnapshot const& spike)
    {
        BotNativeAction::Candidate hook;
        hook.Id.ScopeKey = board.CurrentScope.Key();
        hook.Id.Strategy = "adaptive_magmaw";
        hook.Id.Mechanic = "launch_native_hook";
        hook.Id.Actor = spike.Guid;
        hook.Id.EventGeneration = board.Revision;
        hook.ActionPriority = BotActionArbitration::Priority::Mechanic;
        hook.Utility = 400.0f;
        hook.ExpiresAtMs = board.ObservedAtMs + 500;
        hook.Action = BotNativeAction::VehicleAction{
            vehicle.Entry == PincerLeftEntry ? 77917u : 77941u,
            spike.Guid };
        return hook;
    }

    static BotNativeAction::Candidate BuildMountCandidate(
        Blackboard const& board, ActorSnapshot const& boss)
    {
        BotNativeAction::Candidate mount;
        mount.Id.ScopeKey = board.CurrentScope.Key();
        mount.Id.Strategy = "adaptive_magmaw";
        mount.Id.Mechanic = "mount_free_pincer";
        mount.Id.Actor = boss.Guid;
        mount.Id.EventGeneration = board.Revision;
        mount.ActionPriority = BotActionArbitration::Priority::Mechanic;
        mount.Utility = 350.0f;
        mount.ExpiresAtMs = board.ObservedAtMs + 500;
        mount.Action = BotNativeAction::SpellClick{ boss.Guid };
        return mount;
    }

    static std::optional<BotNativeAction::Candidate> ProposeHookInteraction(
        Blackboard const& board, ActorSnapshot const& bot,
        ActorSnapshot const& boss, ObjectGuid botGuid)
    {
        MagmawHookAssignment const assignment = ResolveHookAssignment(board,
            bot, botGuid);
        if (!assignment.Assigned)
            return std::nullopt;
        if (assignment.Vehicle && assignment.Spike
            && IsPincerVehicle(*assignment.Vehicle))
            return BuildHookCandidate(board, *assignment.Vehicle,
                *assignment.Spike);
        if (boss.Interactable && bot.VehicleGuid.IsEmpty())
            return BuildMountCandidate(board, boss);
        return std::nullopt;
    }

    static std::optional<BotNativeAction::Candidate> ProposeHookPreposition(
        Blackboard const& board, ActorSnapshot const& bot,
        ActorSnapshot const& boss, ObjectGuid botGuid)
    {
        MagmawHookAssignment const assignment = ResolveHookAssignment(board,
            bot, botGuid);
        if (!assignment.Assigned || assignment.Vehicle || boss.Interactable
            || !PincerWarningObserved(board)
            || Distance2d(bot.Position, boss.Position)
                <= HookInteractionDistance)
            return std::nullopt;

        std::optional<Vector3> const destination =
            ResolveHookApproachDestination(board, bot, boss);
        if (!destination)
            return std::nullopt;
        return BuildPointMovement(board, bot, *destination,
            "pincer_preposition", BotActionArbitration::Priority::Mechanic,
            365.0f);
    }

    static std::optional<BotNativeAction::Candidate> ProposeHookApproach(
        Blackboard const& board, ActorSnapshot const& bot,
        ActorSnapshot const& boss, ObjectGuid botGuid)
    {
        MagmawHookAssignment const assignment = ResolveHookAssignment(board,
            bot, botGuid);
        if (!assignment.Assigned || assignment.Vehicle || !boss.Interactable
            || Distance2d(bot.Position, boss.Position)
                <= HookInteractionDistance)
            return std::nullopt;

        std::optional<Vector3> const destination =
            ResolveHookApproachDestination(board, bot, boss);
        if (!destination)
            return std::nullopt;
        return BuildPointMovement(board, bot, *destination,
            "pincer_approach", BotActionArbitration::Priority::Mechanic,
            375.0f);
    }

    static bool HasAura(ActorSnapshot const& actor, uint32 spellId)
    {
        return std::any_of(actor.Auras.begin(), actor.Auras.end(),
            [spellId](AuraSnapshot const& aura) { return aura.SpellId == spellId; });
    }

    static float Distance2d(Vector3 const& left, Vector3 const& right)
    {
        float const dx = left.X - right.X;
        float const dy = left.Y - right.Y;
        return std::sqrt(dx * dx + dy * dy);
    }

    static ActorSnapshot const* FindActorByEntry(Blackboard const& board,
        uint32 entry)
    {
        auto find = [entry](std::vector<ActorSnapshot> const& actors)
            -> ActorSnapshot const*
        {
            auto itr = std::find_if(actors.begin(), actors.end(),
                [entry](ActorSnapshot const& actor)
                {
                    return actor.Alive && actor.Entry == entry;
                });
            return itr == actors.end() ? nullptr : &*itr;
        };
        if (ActorSnapshot const* actor = find(board.Hostiles))
            return actor;
        if (ActorSnapshot const* actor = find(board.Summons))
            return actor;
        return find(board.Interactables);
    }

    static BotNativeAction::Candidate MoveAway(Blackboard const& board,
        ActorSnapshot const& bot, ActorSnapshot const& danger,
        std::string mechanic, float exitDistance)
    {
        float dx = bot.Position.X - danger.Position.X;
        float dy = bot.Position.Y - danger.Position.Y;
        float length = std::sqrt(dx * dx + dy * dy);
        if (length < 0.01f)
        {
            dx = std::cos(bot.Facing);
            dy = std::sin(bot.Facing);
            length = 1.0f;
        }
        BotNativeAction::Candidate candidate;
        candidate.Id.ScopeKey = board.CurrentScope.Key();
        candidate.Id.Strategy = "adaptive_magmaw";
        candidate.Id.Mechanic = std::move(mechanic);
        candidate.Id.Actor = danger.Guid;
        candidate.Id.EventGeneration = board.Revision;
        candidate.ActionPriority = BotActionArbitration::Priority::Survival;
        candidate.Utility = 450.0f;
        candidate.ExpiresAtMs = board.ObservedAtMs + 750;
        candidate.Action = BotNativeAction::Move{
            danger.Position.X + dx / length * exitDistance,
            danger.Position.Y + dy / length * exitDistance,
            bot.Position.Z };
        return candidate;
    }
};
}

#endif
