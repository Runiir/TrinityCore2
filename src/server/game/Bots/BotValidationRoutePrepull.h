#ifndef TRINITY_BOT_VALIDATION_ROUTE_PREPULL_H
#define TRINITY_BOT_VALIDATION_ROUTE_PREPULL_H

// Pure decisions for the prepull setup gate: a raid route's staging node
// (the first regroup or travel node before any pull) of a scenario that opts
// in (row field prepull_setup_gate, emitted only for composition/canonical
// scenarios, so accepted legacy routes keep their exact timing) completes
// only once
// every living member's persistent setup (stances, forms, armors, aspects,
// seals, shields, permanent pets, raid poisons: the member's own
// TryEnsurePersistentCombatSetup) is ready or it has none. Seeded shards
// spawn at their staging anchor and used to advance on arrival, so the first
// pull came before any of it. The gate never waits in combat: a pulled group
// fights as before and the wait restarts afterwards. A member still not set
// up after SetupTimeoutMs of out-of-combat waiting fails the attempt typed.

#include <cstddef>
#include <cstdint>
#include <string>

namespace BotValidationRoutePrepull
{
constexpr std::uint64_t SetupTimeoutMs = 45000;
constexpr char const* TimeoutPrefix = "route_prepull_setup_timeout:";
// A member dead this long at a gated staging node (out of combat, no native
// wipe recovery pending, someone alive) is named instead of the generic
// progress plateau. The clock runs only while the member is dead and NOT in a
// known death-recovery episode (ghost, release requested, runback in
// progress): a released member's graveyard-to-portal runback never counts.
constexpr std::uint64_t DeadMemberGraceMs = 120000;
constexpr char const* DeadMemberPrefix = "route_prepull_member_dead:";

inline bool IsStagingKind(std::string const& kind)
{
    return kind == "regroup" || kind == "travel";
}

inline bool IsPullKind(std::string const& kind)
{
    return kind == "trash" || kind == "boss";
}

// The node at `index` is a staging node: a regroup or travel node that no
// trash or boss node precedes in the route. `Nodes` holds objects with a
// string member `Kind` (the route manifest's nodes).
template <typename Nodes>
bool IsStagingNode(Nodes const& nodes, std::size_t index)
{
    if (index >= nodes.size() || !IsStagingKind(nodes[index].Kind))
        return false;
    for (std::size_t i = 0; i < index; ++i)
        if (IsPullKind(nodes[i].Kind))
            return false;
    return true;
}

// The gate applies to a staging node of a scenario that opted in: nodes also
// carry a bool member `PrepullSetupGate`.
template <typename Nodes>
bool GateApplies(Nodes const& nodes, std::size_t index)
{
    return IsStagingNode(nodes, index) && nodes[index].PrepullSetupGate;
}

enum class SetupStep : std::uint8_t { Ready, Wait, Timeout };

// One arrived, out-of-combat member: ready when its setup has nothing left
// to do; otherwise it keeps setting up until the timeout since it began
// waiting (`waitingSinceMs`, set on its first pending observation).
inline SetupStep DecideSetup(bool setupPending, std::uint64_t waitingSinceMs,
    std::uint64_t nowMs)
{
    if (!setupPending)
        return SetupStep::Ready;
    return waitingSinceMs && nowMs >= waitingSinceMs + SetupTimeoutMs
        ? SetupStep::Timeout : SetupStep::Wait;
}

// The dead clock after one observation of a dead member: stopped (0) while
// it is recovering, else started at its first such observation.
inline std::uint64_t DeadMemberClock(bool knownRecovering, std::uint64_t deadSinceMs,
    std::uint64_t nowMs)
{
    if (knownRecovering)
        return 0;
    return deadSinceMs ? deadSinceMs : nowMs;
}

inline bool DeadMemberBlocks(bool anyAlive, bool anyInCombat, bool nativeRecoveryPending,
    std::uint64_t deadSinceMs, std::uint64_t nowMs)
{
    return anyAlive && !anyInCombat && !nativeRecoveryPending && deadSinceMs
        && nowMs >= deadSinceMs + DeadMemberGraceMs;
}

inline std::string DeadMemberReason(std::uint64_t guid)
{
    return std::string(DeadMemberPrefix) + std::to_string(guid);
}

inline std::string TimeoutReason(std::uint64_t guid, std::string const& missing)
{
    return std::string(TimeoutPrefix) + std::to_string(guid) + ":"
        + (missing.empty() ? std::string("persistent_setup") : missing);
}
}

#endif
