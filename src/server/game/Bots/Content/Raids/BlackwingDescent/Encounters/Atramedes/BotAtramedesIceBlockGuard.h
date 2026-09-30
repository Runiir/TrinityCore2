#ifndef TRINITY_BOT_ATRAMEDES_ICE_BLOCK_GUARD_H
#define TRINITY_BOT_ATRAMEDES_ICE_BLOCK_GUARD_H

// Ice Block is strictly once per fight (user raid experience, 2026-09-25:
// "It can do this only once per fight because of the Ice Block cooldown").
// The plays (BotAtramedesIceBlock.h) read readiness from the published
// 300 s cooldown only, so in a fight that outlasts the cooldown the mage
// would be ready again and play the rescue a second time. This guard is the
// memory that keeps the rule explicit: it records that an Ice Block was
// seen in the fight, and every play treats Ice Block as spent from then on.
//
// Scope: per cohort and attempt id (ObservationAttempt::AttemptId). A different
// attempt replaces the record, in the same instance too. A snapshot of another
// cohort or attempt, or off Atramedes' encounter node, is never observed, so a
// cohort that never runs Atramedes (Stonecore, calibration, legacy Magmaw)
// gets no record. The strategy reads it by the snapshot's cohort and attempt
// id.
// The memory belongs to the fight, not to the combat-log recording: the start
// lifecycle (ObservationAttempt::Lifecycle, CohortRuntime::CombatLogEpoch) is
// not part of the record's identity. `.botexp start` on an active cohort (an
// AlwaysOnAutonomy default cohort) advances the lifecycle by ResetCombatLog
// while Atramedes stays engaged, and must not hand the mage a second Ice
// Block. The record ends only with the fight:
// - Evidence: any living player under Ice Block (45438) while Atramedes is
//   engaged. A block seen before the pull (trash) is another fight's and
//   counts for nothing.
// - A new pull: Atramedes in his snapshot but not in combat (PrePull, the
//   respawn or evade after a wipe) clears the record; Atramedes absent from a
//   snapshot neither spends nor clears it.
// - A wipe: the snapshot's wipe generation (Scope::WipeGeneration) moved since
//   the record's last snapshot, even if no snapshot caught the boss out of
//   combat.
// - A new attempt id replaces the record.
// One process guard (ProcessIceBlockGuard) is fed by the kernel adapter
// (BotWorldPopulationMgrAtramedesCandidates.cpp) on every bot decision and
// read by the strategy; a replay or test passes its own instance.
// Standard library and the snapshot only.

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesFacts.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesObservationExport.h"
#include <cstdint>
#include <map>
#include <mutex>
#include <string>

namespace BotEncounter::Atramedes
{
class IceBlockGuard
{
public:
    // The cohort's encounter snapshot, offered by one bot decision of the
    // cohort's `attempt`. Every bot of the cohort offers the same snapshot:
    // the marking is idempotent.
    void Observe(std::string const& cohortId, ObservationAttempt attempt, Blackboard const& board)
    {
        Scope const& scope = board.CurrentScope;
        if (!attempt.AttemptId || scope.CohortId != cohortId || scope.AttemptId != attempt.AttemptId
            || board.Route.NodeId != EncounterNode)
            return;
        ActorSnapshot const* boss = FindBoss(board);
        if (!boss)
            return;
        std::lock_guard<std::mutex> lock(_mutex);
        Record& record = _cohorts[cohortId];
        // Only a new attempt id starts a new record: a changed lifecycle with
        // the same attempt id is the same fight (see the scope above).
        if (record.AttemptId != attempt.AttemptId)
        {
            record = Record();
            record.AttemptId = attempt.AttemptId;
            record.WipeGeneration = scope.WipeGeneration;
        }
        else if (record.WipeGeneration != scope.WipeGeneration)
        {
            // A wipe ended the fight the record remembers.
            record.Spent = false;
            record.WipeGeneration = scope.WipeGeneration;
        }
        if (!boss->InCombat)
        {
            record.Spent = false;
            return;
        }
        for (ActorSnapshot const& player : board.Players)
            if (player.Alive && FindAura(player, IceBlockAura))
                record.Spent = true;
    }

    // Ice Block was used in the fight of this cohort attempt.
    bool Spent(std::string const& cohortId, std::uint64_t attemptId) const
    {
        std::lock_guard<std::mutex> lock(_mutex);
        auto const found = _cohorts.find(cohortId);
        return found != _cohorts.end() && attemptId
            && found->second.AttemptId == attemptId && found->second.Spent;
    }

private:
    struct Record
    {
        std::uint64_t AttemptId = 0;
        std::uint32_t WipeGeneration = 0;
        bool Spent = false;
    };

    mutable std::mutex _mutex;
    std::map<std::string, Record> _cohorts;
};

inline IceBlockGuard& ProcessIceBlockGuard()
{
    static IceBlockGuard guard;
    return guard;
}
}

#endif
