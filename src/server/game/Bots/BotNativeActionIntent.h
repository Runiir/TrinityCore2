#ifndef TRINITY_BOT_NATIVE_ACTION_INTENT_H
#define TRINITY_BOT_NATIVE_ACTION_INTENT_H

#include "Bots/BotActionArbiter.h"
#include "ObjectGuid.h"
#include <string>
#include <type_traits>
#include <variant>

namespace BotNativeAction
{
struct CastSpell { ObjectGuid Target; uint32 SpellId = 0; };
struct StartAttack { ObjectGuid Target; bool Melee = true; };
struct StopAttack { };
struct Move { float X = 0.0f; float Y = 0.0f; float Z = 0.0f; };
struct GossipOpen { ObjectGuid Target; };
struct GossipSelect { ObjectGuid Target; uint32 MenuId = 0; uint32 OptionId = 0; };
struct SpellClick { ObjectGuid Target; };
struct GameObjectUse { ObjectGuid Target; };
struct VehicleEnter { ObjectGuid Target; int8 Seat = -1; };
struct VehicleAction { uint32 SpellId = 0; ObjectGuid Target; };
struct VehicleExit { };
struct PetCommand { ObjectGuid Pet; ObjectGuid Target; uint32 Command = 0; };
struct UseItem { ObjectGuid Item; ObjectGuid Target; };
struct ReleaseSpirit { };
struct ReclaimCorpse { ObjectGuid Corpse; };

using Intent = std::variant<CastSpell, StartAttack, StopAttack, Move,
    GossipOpen, GossipSelect, SpellClick, GameObjectUse, VehicleEnter, VehicleAction,
    VehicleExit, PetCommand, UseItem, ReleaseSpirit, ReclaimCorpse>;

inline BotActionArbitration::ResourceMask RequiredResources(Intent const& intent)
{
    using namespace BotActionArbitration;
    return std::visit([](auto const& action) -> ResourceMask
    {
        using T = std::decay_t<decltype(action)>;
        if constexpr (std::is_same_v<T, Move>)
            return Uses(Resource::Movement);
        if constexpr (std::is_same_v<T, CastSpell>)
            return Uses(Resource::GlobalCooldown, Resource::Cast, Resource::Target);
        if constexpr (std::is_same_v<T, StartAttack> || std::is_same_v<T, StopAttack>)
            return Uses(Resource::Target);
        if constexpr (std::is_same_v<T, PetCommand>)
            return Uses(Resource::Pet, Resource::Target);
        if constexpr (std::is_same_v<T, VehicleAction>)
            return Uses(Resource::Cast, Resource::Target);
        if constexpr (std::is_same_v<T, UseItem>)
            return Uses(Resource::GlobalCooldown, Resource::Cast, Resource::Target);
        if constexpr (std::is_same_v<T, GossipOpen>
            || std::is_same_v<T, GossipSelect>
            || std::is_same_v<T, SpellClick>
            || std::is_same_v<T, GameObjectUse>
            || std::is_same_v<T, VehicleEnter>
            || std::is_same_v<T, VehicleExit>
            || std::is_same_v<T, ReleaseSpirit>
            || std::is_same_v<T, ReclaimCorpse>)
            return Uses(Resource::Interaction);
        return Uses(Resource::None);
    }, intent);
}

struct CandidateIdentity
{
    std::string ScopeKey;
    std::string Strategy;
    std::string Mechanic;
    ObjectGuid Actor;
    uint64 EventGeneration = 0;

    std::string Key() const
    {
        return ScopeKey + ":" + Strategy + ":" + Mechanic + ":"
            + Actor.ToString() + ":" + std::to_string(EventGeneration);
    }
};

struct Candidate
{
    CandidateIdentity Id;
    BotActionArbitration::Priority ActionPriority = BotActionArbitration::Priority::Idle;
    float Utility = 0.0f;
    uint64 ExpiresAtMs = 0;
    Intent Action;

    BotActionArbitration::ResourceMask Resources() const
    {
        return RequiredResources(Action);
    }
};
}

#endif
