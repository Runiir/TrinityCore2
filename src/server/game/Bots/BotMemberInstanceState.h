#ifndef TRINITY_BOT_MEMBER_INSTANCE_STATE_H
#define TRINITY_BOT_MEMBER_INSTANCE_STATE_H

// Native instance validity and gear wear of one cohort member (round 2,
// Blackwing Descent 10N, Nefarian: the homebind pin loop).
//
// Raid-shard provisioning writes every character at the raid's start
// position (map 669) with instance_id 0. Player::LoadFromDB therefore
// creates a fresh, unbound instance of the raid for the ungrouped bot and
// sets m_InstanceValid = false (no raid group). Group::AddMember (the seed
// leader's Group::Create while the group is still a party; every later member
// against that stray instance, not the seeded one its group is bound to)
// re-evaluates it against that same wrong map, before BotMgrLoading moves
// the bot into its destination instance. Nothing re-evaluates it after the
// bot enters the seeded instance, so every member keeps m_InstanceValid ==
// false. Player::UpdateHomebindTime then calls RepopAtGraveyard on every
// update once its 60 s timer expires: the cross-map graveyard teleport is
// refused for a bot session, and on a transport (Nefarian's platform) its
// `|| GetTransport()` clause resurrects the member at 50% health and mana,
// rage 0, every tick.
//
// Seeded-lockout admission re-evaluates the flag natively
// (CheckInstanceValidity) once the member stands in its final instance, and
// fails closed when it still reads invalid; an admitted attempt fails closed
// on the first member that reads invalid again. The readings are exported
// per member in `.botauto diagnose` and the raid-runtime roster.
//
// Pure: no game state is read here (BotMemberInstanceState.cpp reads it).

#include "Define.h"

#include <iomanip>
#include <sstream>
#include <string>
#include <vector>

class Player;

namespace BotMemberInstanceState
{
// One worn item: ITEM_FIELD_DURABILITY and ITEM_FIELD_MAXDURABILITY.
struct Durability
{
    uint32 Current = 0;
    uint32 Max = 0;
};

// Lowest current/max over the items that wear (max > 0). False when no item
// wears: there is no reading, never an assumed 1.
inline bool MinDurabilityFraction(std::vector<Durability> const& items, float& fraction)
{
    bool found = false;
    float lowest = 1.0f;
    for (Durability const& item : items)
    {
        if (!item.Max)
            continue;
        float const value = item.Current >= item.Max ? 1.0f : float(item.Current) / float(item.Max);
        lowest = found ? (value < lowest ? value : lowest) : value;
        found = true;
    }
    if (found)
        fraction = lowest;
    return found;
}

struct Reading
{
    // A loaded Player was read; nothing below is meaningful otherwise.
    bool Loaded = false;
    // Player::m_InstanceValid and Player::m_HomebindTimer.
    bool InstanceValid = false;
    uint32 HomebindTimerMs = 0;
    bool DurabilityKnown = false;
    float MinDurability = 0.0f;
};

// `,"instance_valid":...,"homebind_timer_ms":...,"min_durability_fraction":...`.
// A member that could not be read exports null for every field, never a
// default that looks valid.
inline std::string FieldsJson(Reading const& reading)
{
    std::ostringstream json;
    if (!reading.Loaded)
    {
        json << ",\"instance_valid\":null,\"homebind_timer_ms\":null,\"min_durability_fraction\":null";
        return json.str();
    }
    json << ",\"instance_valid\":" << (reading.InstanceValid ? "true" : "false")
         << ",\"homebind_timer_ms\":" << reading.HomebindTimerMs
         << ",\"min_durability_fraction\":";
    if (reading.DurabilityKnown)
        json << std::fixed << std::setprecision(4) << reading.MinDurability;
    else
        json << "null";
    return json.str();
}

// The same fields as one object: `{"instance_valid":...,...}`.
inline std::string ObjectJson(Reading const& reading)
{
    return "{" + FieldsJson(reading).substr(1) + "}";
}

// Seeded-lockout admission (CohortContext::VerifyAdmission), per member
// after the group-bind check: `revalidated` is CheckInstanceValidity(false)
// evaluated in the member's final instance.
constexpr char const* AdmissionInvalidPrefix = "seeded_lockout_member_instance_invalid:";

inline std::string AdmissionFailure(bool revalidated, uint32 guid)
{
    return revalidated ? std::string() : AdmissionInvalidPrefix + std::to_string(guid);
}

// An admitted attempt: one member as the active cohort observation sees it.
struct ActiveFacts
{
    bool LockoutAttached = false;
    bool LockoutAdmitted = false;
    uint64 LockoutAttemptId = 0;
    uint64 CohortAttemptId = 0;
    // Loaded, in the world and in the cohort's original instance (members
    // elsewhere are owned by the typed recovery-transit checks).
    bool InOriginalInstance = false;
    bool InstanceValid = false;
};

enum class ActiveVerdict : uint8
{
    NotApplicable, // no seeded lockout on this cohort: unchanged path
    Valid,
    AdmissionMissing,
    InstanceInvalid
};

constexpr char const* ActiveAdmissionMissingReason = "validation_active_seeded_lockout_admission_missing";
constexpr char const* ActiveInstanceInvalidReason = "validation_active_seeded_lockout_member_instance_invalid";

inline ActiveVerdict EvaluateActive(ActiveFacts const& facts)
{
    if (!facts.LockoutAttached)
        return ActiveVerdict::NotApplicable;
    // An active attempt of a seeded cohort holds this attempt's verified
    // admission; anything else is missing evidence.
    if (!facts.LockoutAdmitted || !facts.CohortAttemptId
        || facts.LockoutAttemptId != facts.CohortAttemptId)
        return ActiveVerdict::AdmissionMissing;
    if (facts.InOriginalInstance && !facts.InstanceValid)
        return ActiveVerdict::InstanceInvalid;
    return ActiveVerdict::Valid;
}

// The typed attempt failure for a verdict; nullptr when the member passes.
inline char const* ActiveFailureReason(ActiveVerdict verdict)
{
    switch (verdict)
    {
        case ActiveVerdict::AdmissionMissing: return ActiveAdmissionMissingReason;
        case ActiveVerdict::InstanceInvalid: return ActiveInstanceInvalidReason;
        default: return nullptr;
    }
}

// Live readings (BotMemberInstanceState.cpp). A null or unloaded member
// reads as not loaded.
Reading Read(Player const* bot);
// `.botauto diagnose`: ObjectJson of the member's reading.
std::string MemberObjectJson(Player const* bot);
// Raid-runtime roster: FieldsJson of the loaded bot with this GUID counter.
std::string RosterFieldsJson(uint32 guidCounter);
}

#endif
