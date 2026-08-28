#ifndef TRINITY_BOT_ADAPTIVE_MAGMAW_STRATEGY_H
#define TRINITY_BOT_ADAPTIVE_MAGMAW_STRATEGY_H

#include "Bots/BotEncounterBlackboard.h"
#include "Bots/BotNativeActionIntent.h"
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
    // Magmaw prefers Pillar targets at least combat-reach + 15 yards away.
    // Its configured combat reach is 15 yards, so only the fixed mobile-DPS
    // bait team belongs outside 30 yards.  Healers and ordinary ranged DPS
    // use the support stack inside that preference boundary.
    static constexpr float RangedStackDistance = 30.0f;
    static constexpr float SupportStackDistance = 22.0f;
    static constexpr float RangedStackLateralOffset = 12.0f;
    static constexpr float RangedStackTolerance = 4.0f;
    // Keep a remote parasite from replacing the encounter target.  The
    // native spell/range/LOS gates remain authoritative; this is only the
    // strategy's actionable ranged envelope so a failed add cannot suppress
    // ordinary damage indefinitely.
    static constexpr float RangedParasiteTargetDistance = 35.0f;

    AdaptiveMagmawPlan Propose(Blackboard const& board, ObjectGuid botGuid,
        std::string_view role) const
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
            // Formation/catch-up must remain actionable before the health
            // gate settles: an injured straggler cannot rejoin the support
            // anchor while its cohort is held in place.
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
            // Only the deterministic main tank may create Magmaw's first
            // offensive action. Other profiles stay suppressed until native
            // combat state or a victim proves that the tank pull landed.
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
            pincerWindow, pincerWarning);
        if (!plan.Movement)
            plan.Movement = ProposeHookPreposition(board, *bot,
                *observed.Boss, botGuid);
        if (!plan.Movement)
            plan.Movement = ProposeHookApproach(board, *bot, *observed.Boss,
                botGuid);
        if (!plan.Movement && !pincerWindow
            && !(IsPillarBaiter(board, botGuid) && HasActivePillar(board)))
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

    struct MagmawRangedAnchors
    {
        Vector3 Support;
        Vector3 Left;
        Vector3 Right;
    };

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

        // The frozen Magmaw roster uses one Marks hunter and one Fire mage as
        // its mobile Pillar/add team. Prefer those exact capabilities over
        // roster order so Affliction, Elemental, and the second Fire mage can
        // keep full boss uptime. Explicit Kite assignments still override
        // this deterministic fallback.
        constexpr size_t BaiterCount = 2;
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
            if (preferred != dps.end())
                baiters.push_back((*preferred)->Guid);
        }
        for (ActorSnapshot const* member : dps)
            if (baiters.size() < BaiterCount
                && std::find(baiters.begin(), baiters.end(), member->Guid)
                    == baiters.end())
                baiters.push_back(member->Guid);

        auto const baiter = std::find(baiters.begin(), baiters.end(), botGuid);
        if (baiter == baiters.end())
            return std::nullopt;
        return size_t(std::distance(baiters.begin(), baiter));
    }

    static bool IsPillarBaiter(Blackboard const& board, ObjectGuid botGuid)
    {
        for (AssignmentLease const& assignment : board.Assignments)
            if (assignment.Kind == AssignmentKind::Kite
                && assignment.AssigneeGuid == botGuid
                && assignment.ExpiresAtMs > board.ObservedAtMs)
                return true;
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
        // The exposed head takes the encounter's native vulnerability bonus.
        // Tanks can attack it too; keeping them on the armored body discards
        // the entire burn window for no threat benefit while Magmaw is pinned.
        if (observed.Head)
            return observed.Head->Guid;
        // Only the fixed mobile team owns parasites. Moving every ranged DPS
        // and healer onto the add pack destroys boss uptime and drags the
        // parasites through the support stack. A remote add must not hold a
        // mobile profile on a target that native range/LOS gates reject.
        if (role == "dps" && IsPillarBaiter(board, botGuid)
            && observed.NearestParasite
            && observed.NearestParasiteDistance
                <= RangedParasiteTargetDistance)
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
        bool const crash = actor.Entry == CrashEntry;
        return actor.Alive && (litCrash || parasite || crash);
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
        ActorSnapshot const& boss, ActorSnapshot const& pillar)
    {
        if (!IsPillarBaiter(board, bot.Guid))
            return std::nullopt;
        std::optional<MagmawRangedAnchors> const anchors =
            ResolveRangedAnchors(board, boss);
        if (!anchors)
            return std::nullopt;
        Vector3 const& destination =
            Distance2d(anchors->Left, pillar.Position)
                >= Distance2d(anchors->Right, pillar.Position)
            ? anchors->Left : anchors->Right;
        if (Distance2d(bot.Position, destination) <= RangedStackTolerance)
            return std::nullopt;
        BotNativeAction::Candidate candidate = BuildPointMovement(
            board, bot, destination, "pillar_bait_switch",
            BotActionArbitration::Priority::Survival, 500.0f);
        // Keep one survival action identity for the complete native Pillar
        // movement.  A board revision is an observation, not a new Pillar;
        // using it here discarded the kernel retry state and allowed a
        // rejected/stale path to fall back to profile movement on the next
        // tick.  The summon GUID is stable for this warning and changes when
        // the next Pillar is selected.
        candidate.Id.Actor = pillar.Guid;
        candidate.Id.EventGeneration = pillar.Guid.GetRawValue();
        // A Pillar bait path is a fixed native point movement.  Do not use
        // the bot's changing current Z as the request's destination: while
        // the spline is in flight that made every tick look like a new path
        // and allowed the impact to land before the baiter reached safety.
        // Keep the route-proven anchor Z stable so the movement lease can be
        // refreshed until native arrival or a bounded planner retry.
        if (BotNativeAction::Move* move =
                std::get_if<BotNativeAction::Move>(&candidate.Action))
        {
            move->Z = destination.Z;
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

    static float ParasiteClearance(Blackboard const& board,
        Vector3 const& point)
    {
        float clearance = 1000.0f;
        auto inspect = [&clearance, &point](ActorSnapshot const& actor)
        {
            if (actor.Alive && IsParasiteEntry(actor.Entry))
                clearance = std::min(clearance,
                    Distance2d(point, actor.Position));
        };
        for (ActorSnapshot const& actor : board.Hostiles)
            inspect(actor);
        for (ActorSnapshot const& actor : board.Summons)
            inspect(actor);
        return clearance;
    }

    static std::optional<BotNativeAction::Candidate> BuildParasiteEscape(
        Blackboard const& board, ActorSnapshot const& bot,
        ActorSnapshot const& boss, ActorSnapshot const& parasite)
    {
        std::optional<MagmawRangedAnchors> const anchors =
            ResolveRangedAnchors(board, boss);
        if (!anchors)
            return MoveAway(board, bot, parasite,
                "parasite_contact_evade", 16.0f);

        std::vector<Vector3 const*> destinations = {
            &anchors->Support, &anchors->Left, &anchors->Right };
        auto closest = std::min_element(destinations.begin(),
            destinations.end(), [&bot](Vector3 const* left,
                Vector3 const* right)
            {
                return Distance2d(bot.Position, *left)
                    < Distance2d(bot.Position, *right);
            });
        Vector3 const* destination = *closest;
        constexpr float SafeClearance = 16.0f;
        if (ParasiteClearance(board, *destination) < SafeClearance)
            destination = *std::max_element(destinations.begin(),
                destinations.end(), [&board](Vector3 const* left,
                    Vector3 const* right)
                {
                    return ParasiteClearance(board, *left)
                        < ParasiteClearance(board, *right);
                });

        if (Distance2d(bot.Position, *destination) <= RangedStackTolerance)
            return std::nullopt;
        BotNativeAction::Candidate candidate = BuildPointMovement(board, bot,
            *destination, "parasite_contact_evade",
            BotActionArbitration::Priority::Survival, 450.0f);
        candidate.Id.Actor = parasite.Guid;
        return candidate;
    }

    static bool IsCrashHazard(ActorSnapshot const& actor)
    {
        return actor.Entry == RoomStalkerEntry || actor.Entry == CrashEntry;
    }

    static bool HasMangleAura(ActorSnapshot const& actor)
    {
        return HasAura(actor, 89773) || HasAura(actor, 78412);
    }

    static bool IsPincerWarningActor(ActorSnapshot const& actor)
    {
        return actor.Alive && (actor.Entry == CrashEntry
            || (actor.Entry == RoomStalkerEntry && HasAura(actor, 87949)));
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
        ActorSnapshot const& boss, bool pincerWindow, bool pincerWarning)
    {
        MagmawHazardObservation const observed = ObserveHazards(board, bot);
        if (observed.Pillar)
        {
            // An assigned hook user keeps the native pincer window unless the
            // user is already standing in the pillar.
            if (pincerWindow)
            {
                if (std::optional<BotNativeAction::Candidate> const pillar =
                        BuildPillarEvade(board, bot, *observed.Pillar))
                    return pillar;
            }
            else
            {
                if (std::optional<BotNativeAction::Candidate> const bait =
                        BuildPillarBaitMove(board, bot, boss, *observed.Pillar))
                    return bait;
                if (std::optional<BotNativeAction::Candidate> const pillar =
                        BuildPillarEvade(board, bot, *observed.Pillar))
                    return pillar;
            }
        }

        // Massive Crash and parasites are lower value than completing an
        // already-open native pincer, except for an immediate Crash escape.
        if (pincerWindow)
        {
            if (std::optional<BotNativeAction::Candidate> const crash =
                    ProposeImmediateCrashDuringPincer(board, bot, boss,
                        observed))
                return crash;
            return std::nullopt;
        }

        if (observed.NearestImmediateHazard
            && observed.NearestImmediateHazardDistance <= 12.0f)
        {
            if (IsCrashHazard(*observed.NearestImmediateHazard))
                return MoveAway(board, bot,
                    *observed.NearestImmediateHazard,
                    "massive_crash_evade", 16.0f);
            return BuildParasiteEscape(board, bot, boss,
                *observed.NearestImmediateHazard);
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
        // Let the native spell-click handler own the effective interaction
        // range. Magmaw's combat reach makes a player-like click valid beyond
        // the strategy's center-distance approach threshold; an out-of-range
        // click remains a retryable native result while the approach candidate
        // is still proposed below.
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
