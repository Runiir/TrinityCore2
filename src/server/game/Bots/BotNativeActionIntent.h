#ifndef TRINITY_BOT_NATIVE_ACTION_INTENT_H
#define TRINITY_BOT_NATIVE_ACTION_INTENT_H

#include "Bots/BotActionArbiter.h"
#include "Bots/BotHazardEscapeEvidence.h"
#include "ObjectGuid.h"
#include <cmath>
#include <optional>
#include <string>
#include <string_view>
#include <type_traits>
#include <variant>

namespace BotNativeAction
{
struct CastSpell { ObjectGuid Target; uint32 SpellId = 0; };
struct Move
{
    float X = 0.0f;
    float Y = 0.0f;
    float Z = 0.0f;
    // Preserve the candidate identity that admitted this movement. The
    // top-level decision label may be replaced by a simultaneous combat
    // candidate later in the same tick.
    std::string IntentReason;
    // Ordinary movement can coexist with instant/mobile combat.  A point
    // escape inside a lethal envelope instead owns cast and GCD resources so
    // a hard cast cannot replace the submitted path in the same kernel tick.
    bool PreemptCasting = false;
    // Optional semantic basis for a point escape. Native diagnostics retain
    // this immutable source snapshot so a terrain-resolved endpoint can be
    // reviewed against the exact hazard. It never changes path Z.
    std::optional<BotWorldMovement::HazardEscapeBasis> HazardEscape;
    // Diagnostic-only copy of the selected arbitration candidate identity.
    // Native movement must never consult this field.
    std::string DiagnosticCandidateKey;

    Move() = default;
    Move(float x, float y, float z) : X(x), Y(y), Z(z) { }
    Move(float x, float y, float z, std::string_view reason)
        : X(x), Y(y), Z(z), IntentReason(reason) { }
    Move(float x, float y, float z, std::string_view reason,
        bool preemptCasting)
        : X(x), Y(y), Z(z), IntentReason(reason),
          PreemptCasting(preemptCasting) { }
};
enum class DirectionalMobilityFacing : uint8
{
    Forward,
    Backward
};
// Blink and Disengage are ordinary self-casts whose travel direction is
// determined by player facing.  Keep the desired travel point in the typed
// intent so the native executor can face first and then submit the real
// non-triggered spell; it may never manufacture the resulting position.
struct DirectionalMobility
{
    float X = 0.0f;
    float Y = 0.0f;
    float Z = 0.0f;
    uint32 SpellId = 0;
    DirectionalMobilityFacing Facing = DirectionalMobilityFacing::Forward;
    std::string IntentReason;
};

inline float DirectionalMobilityFacingAngle(float originX, float originY,
    DirectionalMobility const& action)
{
    constexpr float Pi = 3.14159265358979323846f;
    constexpr float TwoPi = 2.0f * Pi;
    float angle = std::atan2(action.Y - originY, action.X - originX);
    if (action.Facing == DirectionalMobilityFacing::Backward)
        angle += Pi;
    angle = std::fmod(angle, TwoPi);
    return angle < 0.0f ? angle + TwoPi : angle;
}
// Combat resurrection uses dedicated intents because its reservation identity
// must survive selection and be revalidated at the native submission edge.
// Generic Move/CastSpell cannot express that owner/target/spell contract.
struct CombatResApproach
{
    ObjectGuid Target;
    uint32 SpellId = 0;
    uint64 ReservationAtMs = 0;
    uint64 ReservationUntilMs = 0;
};
struct CombatResCast
{
    ObjectGuid Target;
    uint32 SpellId = 0;
    uint64 ReservationAtMs = 0;
    uint64 ReservationUntilMs = 0;
};
struct CombatResAccept
{
    ObjectGuid Target;
    uint32 SpellId = 0;
    uint64 ReservationAtMs = 0;
    uint64 ReservationUntilMs = 0;
};
// A route descent is not a special movement primitive. It is a typed request
// to reconcile ordinary native pathing against a landing and the next route
// goal. The executor must observe departure/landing; it may never manufacture
// a jump, fall, position, or health transition.
struct NativeDescent
{
    float LandingX = 0.0f;
    float LandingY = 0.0f;
    float LandingZ = 0.0f;
    float NextGoalX = 0.0f;
    float NextGoalY = 0.0f;
    float NextGoalZ = 0.0f;
    uint64 RouteGeneration = 0;
    bool HasNextGoal = false;
};
struct GossipOpen { ObjectGuid Target; };
struct GossipSelect { ObjectGuid Target; uint32 MenuId = 0; uint32 OptionId = 0; };
struct SpellClick { ObjectGuid Target; };
struct GameObjectUse { ObjectGuid Target; };
struct AreaTrigger { uint32 TriggerId = 0; };
struct VehicleEnter { ObjectGuid Target; int8 Seat = -1; };
struct VehicleAction { uint32 SpellId = 0; ObjectGuid Target; };
struct VehicleExit { };
struct PetCommand { ObjectGuid Pet; ObjectGuid Target; uint32 Command = 0; };
// Inventory item use is a native player request. SpellId names the exact
// on-use effect selected by the player, while Target may name an owned item
// (weapon poisons/oils) or another ordinary explicit target. The executor
// revalidates both GUIDs against the player's live inventory before handing
// the request to WorldSession.
struct UseItem { ObjectGuid Item; ObjectGuid Target; uint32 SpellId = 0; };
struct ReleaseSpirit { };
struct ReclaimCorpse { ObjectGuid Corpse; };

using Intent = std::variant<CastSpell, Move, DirectionalMobility,
    CombatResApproach,
    CombatResCast, CombatResAccept, NativeDescent,
    GossipOpen, GossipSelect, SpellClick, GameObjectUse, AreaTrigger, VehicleEnter, VehicleAction,
    VehicleExit, PetCommand, UseItem, ReleaseSpirit, ReclaimCorpse>;

inline Intent WithMovementReason(Intent intent, std::string_view reason)
{
    std::visit([reason](auto& action)
    {
        using T = std::decay_t<decltype(action)>;
        if constexpr (std::is_same_v<T, Move>
            || std::is_same_v<T, DirectionalMobility>)
            action.IntentReason = std::string(reason);
    }, intent);
    return intent;
}

inline Intent WithMovementDiagnosticCandidateKey(Intent intent,
    std::string_view candidateKey)
{
    std::visit([candidateKey](auto& action)
    {
        using T = std::decay_t<decltype(action)>;
        if constexpr (std::is_same_v<T, Move>)
            action.DiagnosticCandidateKey = std::string(candidateKey);
    }, intent);
    return intent;
}

inline BotActionArbitration::ResourceMask RequiredResources(Intent const& intent)
{
    using namespace BotActionArbitration;
    return std::visit([](auto const& action) -> ResourceMask
    {
        using T = std::decay_t<decltype(action)>;
        if constexpr (std::is_same_v<T, Move>)
            return action.PreemptCasting
                ? Uses(Resource::Movement, Resource::GlobalCooldown,
                    Resource::Cast)
                : Uses(Resource::Movement);
        if constexpr (std::is_same_v<T, DirectionalMobility>)
            return Uses(Resource::Movement, Resource::GlobalCooldown,
                Resource::Cast);
        if constexpr (std::is_same_v<T, NativeDescent>)
            return Uses(Resource::Movement);
        if constexpr (std::is_same_v<T, CombatResApproach>)
            // Approaching only submits native movement.  It observes the
            // reserved target but does not retarget or consume spell/GCD
            // state, so ordinary damage may continue during the approach.
            return Uses(Resource::Movement);
        if constexpr (std::is_same_v<T, CombatResCast>)
            return Uses(Resource::Movement, Resource::GlobalCooldown,
                Resource::Cast, Resource::Target);
        if constexpr (std::is_same_v<T, CombatResAccept>)
            return Uses(Resource::Interaction, Resource::Target);
        if constexpr (std::is_same_v<T, CastSpell>)
            return Uses(Resource::GlobalCooldown, Resource::Cast, Resource::Target);
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
            || std::is_same_v<T, AreaTrigger>
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
