#ifndef TRINITY_BOT_MAGMAW_BAITER_ROTATION_H
#define TRINITY_BOT_MAGMAW_BAITER_ROTATION_H

#include "Bots/BotEncounterBlackboard.h"
#include "ObjectGuid.h"

#include <algorithm>
#include <cstddef>
#include <map>
#include <mutex>
#include <optional>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace BotEncounter
{
// DPS-064: a real raid rotates parasite bait duty. The Hunter slot stays with
// the roster Hunter; the Fire Mage slot alternates between the two lowest-GUID
// dps Fire Mages, one parasite wave at a time (wave 1 the first, wave 2 the
// second, wave 3 the first again). Only the assignment rotates: geometry,
// lanes and damage are unchanged.
//
// A wave is one pillar/parasite episode: it starts when a living Pillar of
// Flame, a living Lava Parasite or a living player's Parasitic Infection
// (which later releases parasites) is observed, and it ends after
// QuietBoundaryMs with none of them. A dead parasite despawns 2.5 s after
// death, so a shorter gap is observation churn inside the same wave. The next
// wave's baiter is chosen at that boundary, before its pillar can appear, and
// never while a wave is live. A switch that would change the hook riders
// (the hook list excludes the baiters) waits until the Mangle/pincer duty is
// over; if the next wave arrives first, the current baiter keeps it. If the
// other mage is dead or not observed, the current baiter keeps the wave.
struct MagmawBaiterRotation
{
    enum class Reason : uint8
    {
        Initial,
        Alternate,
        AlternateUnavailable,
        SingleMage,
        ActiveMageUnavailable,
        HookDutyKept
    };

    struct Assignment
    {
        uint32 Wave = 0;
        ObjectGuid Mage;
        uint64 AssignedAtMs = 0;
        uint64 Revision = 0;
        Reason Why = Reason::Initial;
    };

    struct Roster
    {
        ObjectGuid FirstMage;
        ObjectGuid SecondMage;
        ObjectGuid Hunter;
    };

    static constexpr char const* EncounterNode = "bwd.magmaw.encounter";
    static constexpr uint32 BossEntry = 41570;
    static constexpr uint32 PillarEntry = 41843;
    static constexpr uint32 ParasiteEntry = 41806;
    static constexpr uint32 ParasiteAltEntry = 42321;
    static constexpr uint32 RoomStalkerEntry = 47196;
    static constexpr uint32 PincerWarningAura = 87949;
    // Native Magmaw publishes the time to its next Mangle under the Massive
    // Crash spell id (0 while the sequence runs; a value above the 95 s
    // repeat is an overdue, wrapped timer).
    static constexpr uint32 MangleTimerSpell = 88253;
    static constexpr uint32 NativeMangleRepeatMs = 95000;
    // Hook riders leave for the wait point 6 s before the seize
    // (HookWaitLeadMs); freeze the rider list well before that.
    static constexpr uint32 HookDutyLeadMs = 15000;
    static constexpr uint64 QuietBoundaryMs = 3000;
    static constexpr std::size_t HistoryCapacity = 16;

    std::string ScopeKey;
    bool Observed = false;
    uint64 LastRevision = 0;
    uint64 LastObservedAtMs = 0;
    ObjectGuid PrimaryMage;
    ObjectGuid AlternateMage;
    ObjectGuid Hunter;
    ObjectGuid ActiveMage;
    // One-based index of the current wave, or of the next one between waves.
    uint32 Wave = 1;
    uint32 CompletedWaves = 0;
    bool WaveObserved = false;
    bool QuietTiming = false;
    uint64 QuietSinceMs = 0;
    bool SwitchPending = false;
    bool PendingDeferred = false;
    uint32 Deferrals = 0;
    char const* LastDeferral = "";
    std::vector<Assignment> History;

    static bool AppliesTo(Blackboard const& board)
    {
        return board.CurrentScope.NodeId == EncounterNode
            || board.Route.NodeId == EncounterNode;
    }

    static bool IsBaitMage(ActorSnapshot const& member)
    {
        return member.Role == "dps" && member.ClassSpec == "fire_mage";
    }

    static bool IsBaitHunter(ActorSnapshot const& member)
    {
        return member.Role == "dps"
            && (member.ClassSpec == "marksmanship_hunter"
                || member.ClassSpec == "survival_hunter");
    }

    // Roster identity only, independent of liveness: a death must not
    // promote another actor into the retained lane mid-wave.
    static Roster ObserveRoster(Blackboard const& board)
    {
        Roster roster;
        for (ActorSnapshot const& member : board.Players)
        {
            uint64 const raw = member.Guid.GetRawValue();
            if (IsBaitMage(member))
            {
                if (member.Guid == roster.FirstMage
                    || member.Guid == roster.SecondMage)
                    continue;
                if (roster.FirstMage.IsEmpty()
                    || raw < roster.FirstMage.GetRawValue())
                {
                    roster.SecondMage = roster.FirstMage;
                    roster.FirstMage = member.Guid;
                }
                else if (roster.SecondMage.IsEmpty()
                    || raw < roster.SecondMage.GetRawValue())
                    roster.SecondMage = member.Guid;
            }
            else if (IsBaitHunter(member) && (roster.Hunter.IsEmpty()
                    || raw < roster.Hunter.GetRawValue()))
                roster.Hunter = member.Guid;
        }
        return roster;
    }

    void Reset(std::string const& scopeKey)
    {
        *this = {};
        ScopeKey = scopeKey;
    }

    std::pair<ObjectGuid, ObjectGuid> Baiters() const
    {
        return { ActiveMage, Hunter };
    }

    // Storage anchor of the shared lane state: stable for the whole scope.
    ObjectGuid LaneStateAnchor() const
    {
        return PrimaryMage.IsEmpty() ? Hunter : PrimaryMage;
    }

    ObjectGuid OtherMage(ObjectGuid mage) const
    {
        return mage == PrimaryMage ? AlternateMage
            : mage == AlternateMage ? PrimaryMage : ObjectGuid();
    }

    // Only a board newer than the last one advances the rotation, so every
    // caller of one snapshot revision sees the same baiter.
    bool Observe(Blackboard const& board)
    {
        if (Observed && board.Revision <= LastRevision)
            return false;
        Observed = true;
        LastRevision = board.Revision;
        LastObservedAtMs = board.ObservedAtMs;
        LatchRoster(board);
        if (ActiveMage.IsEmpty())
        {
            if (PrimaryMage.IsEmpty())
                return true;
            ActiveMage = PrimaryMage;
            Record(board, Reason::Initial);
        }

        if (MechanicPresent(board))
        {
            QuietTiming = false;
            if (SwitchPending)
            {
                SwitchPending = false;
                Record(board, Reason::HookDutyKept);
            }
            WaveObserved = true;
            return true;
        }
        if (WaveObserved)
        {
            if (!QuietTiming)
            {
                QuietTiming = true;
                QuietSinceMs = board.ObservedAtMs;
            }
            if (board.ObservedAtMs < QuietSinceMs + QuietBoundaryMs)
                return true;
            WaveObserved = false;
            QuietTiming = false;
            ++CompletedWaves;
            ++Wave;
            SwitchPending = true;
            PendingDeferred = false;
        }

        char const* const deferral = HookDutyDeferral(board);
        if (SwitchPending)
        {
            if (deferral)
            {
                if (!PendingDeferred)
                    ++Deferrals;
                PendingDeferred = true;
                LastDeferral = deferral;
                return true;
            }
            SwitchPending = false;
            ObjectGuid const other = OtherMage(ActiveMage);
            if (other.IsEmpty())
                Record(board, Reason::SingleMage);
            else if (!MageAvailable(board, other))
                Record(board, Reason::AlternateUnavailable);
            else
            {
                ActiveMage = other;
                Record(board, Reason::Alternate);
            }
        }
        else if (!deferral && !MageAvailable(board, ActiveMage))
        {
            // Between waves only: a dead or absent baiter hands the next
            // wave to a living alternate instead of leaving it unbaited.
            ObjectGuid const other = OtherMage(ActiveMage);
            if (!other.IsEmpty() && MageAvailable(board, other))
            {
                ActiveMage = other;
                Record(board, Reason::ActiveMageUnavailable);
            }
        }
        return true;
    }

    static bool MageAvailable(Blackboard const& board, ObjectGuid guid)
    {
        return std::any_of(board.Players.begin(), board.Players.end(),
            [guid](ActorSnapshot const& member)
            {
                return member.Guid == guid && member.Alive
                    && IsBaitMage(member);
            });
    }

    static bool HasAura(ActorSnapshot const& actor, uint32 spellId)
    {
        return std::any_of(actor.Auras.begin(), actor.Auras.end(),
            [spellId](AuraSnapshot const& aura)
            {
                return aura.SpellId == spellId;
            });
    }

    static bool HasParasiticInfection(ActorSnapshot const& actor)
    {
        for (uint32 spellId : { 78097u, 78941u, 91913u, 94678u, 94679u })
            if (HasAura(actor, spellId))
                return true;
        return false;
    }

    static bool HasMangleAura(ActorSnapshot const& actor)
    {
        for (uint32 spellId : { 89773u, 91912u, 94616u, 94617u, 78412u })
            if (HasAura(actor, spellId))
                return true;
        return false;
    }

    static bool MechanicPresent(Blackboard const& board)
    {
        for (std::vector<ActorSnapshot> const* actors : {
                 &board.Hostiles, &board.Summons, &board.Interactables })
            for (ActorSnapshot const& actor : *actors)
                if (actor.Alive && (actor.Entry == ParasiteEntry
                        || actor.Entry == ParasiteAltEntry
                        || actor.Entry == PillarEntry))
                    return true;
        return std::any_of(board.Players.begin(), board.Players.end(),
            [](ActorSnapshot const& member)
            {
                return member.Alive && HasParasiticInfection(member);
            });
    }

    static bool MangleImminent(ActorSnapshot const& boss)
    {
        MechanicTimerSnapshot const* timer =
            boss.FindMechanicTimer(MangleTimerSpell);
        if (!boss.InCombat || !timer
            || timer->Source != FactSource::NativeInstanceState)
            return false;
        uint32 const dueInMs = timer->SequenceActive
            || timer->RemainingMs > NativeMangleRepeatMs
            ? 0 : timer->RemainingMs;
        return dueInMs <= HookDutyLeadMs;
    }

    // Non-null while the hook riders are being prepared or ride: changing
    // the baiter then would change the rider list mid-duty.
    static char const* HookDutyDeferral(Blackboard const& board)
    {
        for (ActorSnapshot const& member : board.Players)
        {
            if (!member.Alive)
                continue;
            if (!member.VehicleGuid.IsEmpty())
                return "vehicle_seat";
            if (HasMangleAura(member))
                return "mangle_active";
        }
        for (std::vector<ActorSnapshot> const* actors : {
                 &board.Hostiles, &board.Summons, &board.Interactables })
            for (ActorSnapshot const& actor : *actors)
            {
                if (!actor.Alive)
                    continue;
                if (actor.Entry == BossEntry && actor.Interactable)
                    return "pincer_window";
                if (actor.Entry == BossEntry && MangleImminent(actor))
                    return "mangle_imminent";
                if (actor.Entry == RoomStalkerEntry
                    && HasAura(actor, PincerWarningAura))
                    return "pincer_warning";
            }
        return nullptr;
    }

    static char const* ToString(Reason reason)
    {
        switch (reason)
        {
            case Reason::Initial: return "initial";
            case Reason::Alternate: return "alternate";
            case Reason::AlternateUnavailable: return "alternate_unavailable";
            case Reason::SingleMage: return "single_mage";
            case Reason::ActiveMageUnavailable:
                return "active_mage_unavailable";
            case Reason::HookDutyKept: return "hook_duty_kept";
        }
        return "unknown";
    }

private:
    void LatchRoster(Blackboard const& board)
    {
        Roster const roster = ObserveRoster(board);
        if (PrimaryMage.IsEmpty())
        {
            PrimaryMage = roster.FirstMage;
            AlternateMage = roster.SecondMage;
        }
        else if (AlternateMage.IsEmpty())
            AlternateMage = roster.FirstMage != PrimaryMage
                ? roster.FirstMage : roster.SecondMage;
        if (Hunter.IsEmpty())
            Hunter = roster.Hunter;
    }

    void Record(Blackboard const& board, Reason reason)
    {
        if (History.size() >= HistoryCapacity)
            History.erase(History.begin());
        History.push_back({ Wave, ActiveMage, board.ObservedAtMs,
            board.Revision, reason });
    }
};

// Every caller of ResolveFixedBaiters holds only the cohort snapshot, so the
// rotation lives in one encounter-scoped ledger per cohort, reset whenever
// the cohort's scope key (attempt, wipe, route, map, instance) changes.
// Observation is idempotent per snapshot revision.
class MagmawBaiterRotationRegistry
{
public:
    static std::pair<ObjectGuid, ObjectGuid> ObserveBaiters(
        Blackboard const& board)
    {
        std::lock_guard<std::mutex> lock(Mutex());
        MagmawBaiterRotation& rotation = Bind(board);
        rotation.Observe(board);
        return rotation.Baiters();
    }

    static ObjectGuid ObserveLaneStateAnchor(Blackboard const& board)
    {
        std::lock_guard<std::mutex> lock(Mutex());
        MagmawBaiterRotation& rotation = Bind(board);
        rotation.Observe(board);
        return rotation.LaneStateAnchor();
    }

    static std::optional<MagmawBaiterRotation> Find(
        std::string_view scopeKey)
    {
        std::lock_guard<std::mutex> lock(Mutex());
        for (auto const& [cohort, rotation] : Rotations())
            if (!scopeKey.empty() && rotation.ScopeKey == scopeKey)
                return rotation;
        return std::nullopt;
    }

    static void Clear()
    {
        std::lock_guard<std::mutex> lock(Mutex());
        Rotations().clear();
    }

private:
    static MagmawBaiterRotation& Bind(Blackboard const& board)
    {
        std::string const key = board.CurrentScope.Key();
        MagmawBaiterRotation& rotation =
            Rotations()[board.CurrentScope.CohortId];
        if (rotation.ScopeKey != key)
            rotation.Reset(key);
        return rotation;
    }

    static std::map<std::string, MagmawBaiterRotation>& Rotations()
    {
        static std::map<std::string, MagmawBaiterRotation> rotations;
        return rotations;
    }

    static std::mutex& Mutex()
    {
        static std::mutex mutex;
        return mutex;
    }
};
}

#endif
