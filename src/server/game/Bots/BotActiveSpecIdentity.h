#ifndef TRINITY_BOT_ACTIVE_SPEC_IDENTITY_H
#define TRINITY_BOT_ACTIVE_SPEC_IDENTITY_H

// The class spec and role of a raid member follow its ACTIVE talent group
// (round 10, per-boss spec switching in a canonical full raid).
//
// character_bot_pool holds one class_spec and role per character: the talent
// group it was provisioned in. A canonical full raid's route switches members
// between their two talent groups (spec_contract nodes, BotRaidSpecSwitch.h),
// so every identity reader (GetDungeonRole, GetBotClassSpec, the action
// profile's spec inference, the raid roster) first asks this registry. An entry
// exists only for a character a spec_contract node registered, with the
// identity of each of its talent groups; Resolve answers for the group the
// Player has active right now, so the identity flips exactly when the native
// Activate Spec spell runs Player::ActivateSpec, and a character that is never
// registered (every legacy, dungeon, calibration and boss-shard bot) keeps the
// pool identity unchanged.

#include "Define.h"

#include <cstddef>
#include <map>
#include <mutex>
#include <string>
#include <utility>
#include <vector>

namespace BotActiveSpecIdentity
{
struct Identity
{
    std::string ClassSpec;
    std::string Role;
};

using Groups = std::vector<std::pair<uint8, Identity>>;

namespace Detail
{
inline std::mutex& Lock()
{
    static std::mutex lock;
    return lock;
}

inline std::map<uint32, Groups>& Table()
{
    static std::map<uint32, Groups> table;
    return table;
}
}

inline void Register(uint32 guidLow, Groups groups)
{
    std::lock_guard<std::mutex> guard(Detail::Lock());
    Detail::Table()[guidLow] = std::move(groups);
}

inline void Forget(uint32 guidLow)
{
    std::lock_guard<std::mutex> guard(Detail::Lock());
    Detail::Table().erase(guidLow);
}

inline bool IsRegistered(uint32 guidLow)
{
    std::lock_guard<std::mutex> guard(Detail::Lock());
    return Detail::Table().count(guidLow) != 0;
}

// The identity of `activeGroup` for a registered character.
inline bool Resolve(uint32 guidLow, uint8 activeGroup, Identity& out)
{
    std::lock_guard<std::mutex> guard(Detail::Lock());
    auto const itr = Detail::Table().find(guidLow);
    if (itr == Detail::Table().end())
        return false;
    for (auto const& [group, identity] : itr->second)
        if (group == activeGroup)
        {
            out = identity;
            return true;
        }
    return false;
}

// Whether `classSpec` is one of a registered character's talent groups.
inline bool DeclaresClassSpec(uint32 guidLow, std::string const& classSpec)
{
    std::lock_guard<std::mutex> guard(Detail::Lock());
    auto const itr = Detail::Table().find(guidLow);
    if (itr == Detail::Table().end())
        return false;
    for (auto const& [group, identity] : itr->second)
        if (identity.ClassSpec == classSpec)
            return true;
    return false;
}
}

#endif
