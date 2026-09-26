#ifndef TRINITY_BOT_POST_KILL_RECOVERY_H
#define TRINITY_BOT_POST_KILL_RECOVERY_H

// The post-kill recovery window (round 10): pure decisions, no Player,
// InstanceScript or spell system access. After a boss kill no hostile is left
// to hold, yet node completion needs every member alive at the node. The
// combat-res machinery (BotWorldPopulationMgrCombatRes.cpp) is combat-only
// and closed under native_full_wipe_only, so nobody raised the dead: round 8
// killed Nefarian and never completed its node.
//
// On a canonical-composition raid boss node, once the engaged boss is
// recorded killed (the node's boss_killed terminal), the encounter is no
// longer in progress and no hostile activity remains, the window opens:
// - the ordinary out-of-combat resurrection spells count as usable (and
//   Rebirth when ready), cast by any living member that knows one, tanks
//   included (nothing is left to hold);
// - one body per caster, several casters in parallel, healers raised first;
// - a dead member keeps its release for at most ReleaseHoldMs from the
//   window's opening while a caster that could reach it exists; a body no
//   caster can reach (out of range with no liquid-free approach, or out of
//   line of sight: under the Nefarian platform) releases at once and returns
//   (BotValidationRouteRecoveryReturn.h, post-kill return).
// The native spell system stays authoritative: the resurrection request
// stores the caster's position (Player::SetResurrectRequestData) and the
// accepted request teleports the member there (ResurrectUsingRequestData).

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>
#include <vector>

namespace BotPostKillRecovery
{
// Redemption, Resurrection, Ancestral Spirit, Revive (4.3.4 Spell.dbc /
// SpellEffect.dbc: SPELL_EFFECT_RESURRECT at 35%, attribute
// SPELL_ATTR0_NOT_IN_COMBAT_ONLY_PEACEFUL, no in-combat resurrection limit).
constexpr std::uint32_t Redemption = 7328;
constexpr std::uint32_t Resurrection = 2006;
constexpr std::uint32_t AncestralSpirit = 2008;
constexpr std::uint32_t Revive = 50769;

inline bool IsOutOfCombatResurrection(std::uint32_t spellId)
{
    return spellId == Redemption || spellId == Resurrection
        || spellId == AncestralSpirit || spellId == Revive;
}

// A dead member holds its release at most this long after the window opens.
constexpr std::uint64_t ReleaseHoldMs = 90000;
// Decisions the window publishes for a dead member it did not assign.
constexpr char const* CasterPending = "declined_post_kill_caster_pending";
constexpr char const* NoReachableCaster = "declined_post_kill_no_reachable_caster";
// An approach that would enter liquid (a body in the lava) is never walked.
constexpr char const* ApproachThroughLiquid = "declined_post_kill_approach_through_liquid";
// An owner still flagged in combat cannot start a peaceful-only spell yet.
constexpr char const* OwnerInCombat = "declined_owner_in_combat";
// Re-evaluation delays of the published decisions.
constexpr std::uint64_t PendingDecisionMs = 1000;
constexpr std::uint64_t UnreachableDecisionMs = 5000;

struct Scope
{
    std::uint64_t AttemptId = 0;
    std::uint64_t RouteGeneration = 0;
    std::string NodeId;

    bool operator==(Scope const& other) const
    {
        return AttemptId == other.AttemptId && RouteGeneration == other.RouteGeneration
            && NodeId == other.NodeId;
    }
};

struct WindowObservation
{
    Scope Current;
    bool CanonicalRaid = false;
    bool BossNode = false;
    // The node's boss_killed terminal at the current route generation.
    bool BossKillRecorded = false;
    bool EncounterInProgress = false;
    bool HostileActivityActive = false;
    // The hostile observation belongs to the current attempt, generation and
    // node (a stale "inactive" from an earlier node proves nothing).
    bool HostileObservationCurrent = false;
    std::uint64_t NowMs = 0;
};

// Why the window is closed ("" when it is open).
inline char const* ClosedReason(WindowObservation const& observation)
{
    if (!observation.CanonicalRaid)
        return "not_canonical_raid";
    if (!observation.BossNode)
        return "not_boss_node";
    if (!observation.BossKillRecorded)
        return "boss_not_killed";
    if (observation.EncounterInProgress)
        return "encounter_in_progress";
    if (!observation.HostileObservationCurrent)
        return "hostile_observation_stale";
    if (observation.HostileActivityActive)
        return "hostile_activity";
    return "";
}

// The window per scope: opened once (the release hold's clock starts then and
// never restarts in that scope), open while its conditions hold.
struct Latch
{
    Scope Of;
    bool Open = false;
    std::uint64_t OpenedAtMs = 0;
    std::string Reason = "not_observed";
};

enum class Edge : std::uint8_t { None, Opened, Closed };

inline Edge Observe(Latch& latch, WindowObservation const& observation)
{
    bool const wasOpen = latch.Open;
    if (!(latch.Of == observation.Current))
    {
        latch = Latch();
        latch.Of = observation.Current;
    }
    latch.Reason = ClosedReason(observation);
    latch.Open = latch.Reason.empty();
    if (latch.Open && !latch.OpenedAtMs)
        latch.OpenedAtMs = observation.NowMs;
    if (latch.Open == wasOpen)
        return Edge::None;
    return latch.Open ? Edge::Opened : Edge::Closed;
}

inline bool WindowOpen(Latch const& latch, Scope const& current)
{
    return latch.Open && latch.Of == current;
}

// Whether a dead (unreleased) member keeps its release now: the window is
// open in this scope, the bound has not passed, and the window has not found
// that no caster can reach it.
inline bool HoldsRelease(Latch const& latch, Scope const& current,
    std::string_view decision, std::uint64_t nowMs)
{
    return WindowOpen(latch, current) && nowMs < latch.OpenedAtMs + ReleaseHoldMs
        && decision != NoReachableCaster;
}

// A caster's refusal that passes by itself (a cast or GCD finishing, combat
// ending, mana returning, a request settling) keeps the body reachable;
// every other refusal (no path or line of sight, an approach through
// liquid, a spell on a long cooldown, the wrong map or group, a dead or
// unloaded owner) does not.
inline bool DeclineIsTransient(std::string_view reason)
{
    return reason == "declined_owner_casting" || reason == "declined_owner_global_cooldown"
        || reason == "declined_insufficient_power" || reason == OwnerInCombat
        || reason == "declined_approach_reservation_state_drift";
}

// Raise order: healers first (each raised healer raises more), then tanks,
// then the rest.
inline std::uint32_t TargetPriority(std::string_view role)
{
    return role == "healer" ? 300 : role == "tank" ? 250 : 100;
}

enum class Outcome : std::uint8_t { Assigned, Pending, Unreachable };

struct Assignment
{
    Outcome Result = Outcome::Unreachable;
    // Index into the owner candidates when Assigned.
    std::size_t Owner = 0;
};

// Targets in raise order, owner candidates in preference order (one row per
// owner and spell: the out-of-combat spells, without a cooldown, before
// Rebirth). Each caster (ownerKeys, one per candidate row) takes at most one
// body; casters already reserving a body are busy. usable(target, owner,
// reason) is the native owner check of that pairing. A body goes to the
// first free usable caster; otherwise it is Pending while some caster could
// serve it (usable but busy, or refusing only transiently), else Unreachable.
template <typename Usable>
std::vector<Assignment> Assign(std::size_t targetCount,
    std::vector<std::uint64_t> const& ownerKeys, std::vector<std::uint64_t> busy,
    Usable&& usable)
{
    std::vector<Assignment> out(targetCount);
    for (std::size_t target = 0; target < targetCount; ++target)
    {
        bool reachable = false;
        for (std::size_t owner = 0; owner < ownerKeys.size(); ++owner)
        {
            std::string reason;
            bool const ok = usable(target, owner, reason);
            bool const free = std::find(busy.begin(), busy.end(), ownerKeys[owner])
                == busy.end();
            if (ok && free)
            {
                out[target] = { Outcome::Assigned, owner };
                busy.push_back(ownerKeys[owner]);
                break;
            }
            reachable = reachable || ok || DeclineIsTransient(reason);
        }
        if (out[target].Result != Outcome::Assigned)
            out[target].Result = reachable ? Outcome::Pending : Outcome::Unreachable;
    }
    return out;
}

// The node's boss was recorded killed at this route generation: any member's
// boss_killed terminal (both kill recorders set it on every member).
template <typename States>
bool BossKillRecorded(States const& states, std::uint64_t routeGeneration)
{
    for (auto const& state : states)
        if (state.ValidationRouteTerminalState
            && state.ValidationRouteTerminalGeneration == routeGeneration
            && state.ValidationRouteTerminalReason == "boss_killed")
            return true;
    return false;
}

// An approach sampled along its path (in walking order from where the
// caster stands): its destination is the first sample inside the cast
// envelope (within range of the body with line of sight), provided no
// earlier sample lies in liquid. The caster walks to that dry point, never
// to the body (a body in the lava lies past it). inLiquid(i) and
// inEnvelope(i) observe sample i. Returns `samples` when refused: liquid
// first, or a path that never reaches the envelope.
template <typename InLiquid, typename InEnvelope>
std::size_t ApproachDestination(std::size_t samples, InLiquid&& inLiquid, InEnvelope&& inEnvelope)
{
    for (std::size_t sample = 0; sample < samples; ++sample)
    {
        if (inLiquid(sample))
            return samples;
        if (inEnvelope(sample))
            return sample;
    }
    return samples;
}

// The window's own deadline: ReleaseHoldMs after it opened in this scope.
// Past it no body is reserved any more, and every post-kill reservation (one
// made since the opening while the window is open, or for an out-of-combat
// spell) ends: approach, submitted cast and the dead member's wait alike.
// In-combat reservations are never bound by it.
constexpr char const* Deadline = "declined_post_kill_deadline";

inline bool PastDeadline(Latch const& latch, Scope const& current, std::uint64_t nowMs)
{
    return latch.Of == current && latch.OpenedAtMs
        && nowMs >= latch.OpenedAtMs + ReleaseHoldMs;
}

inline bool ReservationPastDeadline(Latch const& latch, Scope const& current,
    std::uint32_t spellId, std::uint64_t reservationAtMs, std::uint64_t nowMs)
{
    return PastDeadline(latch, current, nowMs) && reservationAtMs >= latch.OpenedAtMs
        && (latch.Open || IsOutOfCombatResurrection(spellId));
}

// The dead member's wait on its reservation (after the window's release
// hold, BotWorldPopulationMgrUpdateDeath.cpp): wait while the typed intent is
// current, the post-kill deadline has not passed and the owner is usable;
// otherwise decline (Reason empty: the owner check's own refusal) and go on
// to the ordinary release. No reservation: nothing to wait for.
enum class ReservationStep : std::uint8_t { None, Wait, Decline };

struct ReservationVerdict
{
    ReservationStep Step = ReservationStep::None;
    char const* Reason = "";
};

inline ReservationVerdict DecideReservationWait(bool reservationPresent, bool intentCurrent,
    bool postKillPastDeadline, bool ownerUsable)
{
    if (!reservationPresent)
        return {};
    if (!intentCurrent)
        return { ReservationStep::Decline, "declined_typed_intent_not_current" };
    if (postKillPastDeadline)
        return { ReservationStep::Decline, Deadline };
    if (!ownerUsable)
        return { ReservationStep::Decline, "" };
    return { ReservationStep::Wait, "" };
}
}

#endif
