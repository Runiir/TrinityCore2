#ifndef TRINITY_BOT_ENCOUNTER_BLACKBOARD_H
#define TRINITY_BOT_ENCOUNTER_BLACKBOARD_H

#include "Define.h"
#include "ObjectGuid.h"
#include <algorithm>
#include <map>
#include <optional>
#include <string>
#include <vector>

namespace BotEncounter
{
struct Scope
{
    std::string CohortId;
    uint64 AttemptId = 0;
    uint32 WipeGeneration = 0;
    uint64 RouteGeneration = 0;
    std::string NodeId;
    uint32 MapId = 0;
    uint32 InstanceId = 0;
    std::string EncounterId;

    bool Valid() const
    {
        return !CohortId.empty() && AttemptId && MapId;
    }

    std::string Key() const
    {
        return CohortId + ":" + std::to_string(AttemptId) + ":"
            + std::to_string(WipeGeneration) + ":"
            + std::to_string(RouteGeneration) + ":" + NodeId + ":"
            + std::to_string(MapId) + ":" + std::to_string(InstanceId)
            + ":" + EncounterId;
    }

    friend bool operator==(Scope const& left, Scope const& right)
    {
        return left.CohortId == right.CohortId
            && left.AttemptId == right.AttemptId
            && left.WipeGeneration == right.WipeGeneration
            && left.RouteGeneration == right.RouteGeneration
            && left.NodeId == right.NodeId
            && left.MapId == right.MapId
            && left.InstanceId == right.InstanceId
            && left.EncounterId == right.EncounterId;
    }
};

enum class FactSource : uint8
{
    VisibleUnitState,
    VisibleAura,
    VisibleCast,
    CombatLogEvent,
    GroupState,
    NativeInstanceState,
    RouteManifest
};

enum class ActorKind : uint8
{
    Player,
    Pet,
    Hostile,
    Summon,
    Interactable
};

struct Vector3
{
    float X = 0.0f;
    float Y = 0.0f;
    float Z = 0.0f;
};

struct AuraSnapshot
{
    uint32 SpellId = 0;
    ObjectGuid CasterGuid;
    uint8 Stacks = 0;
    uint64 ExpiresAtMs = 0;
};

struct CastSnapshot
{
    uint32 SpellId = 0;
    ObjectGuid TargetGuid;
    uint64 ObservedAtMs = 0;
    bool Channeled = false;
    bool Interruptible = false;
};

struct ActorSnapshot
{
    ObjectGuid Guid;
    uint32 Entry = 0;
    ActorKind Kind = ActorKind::Hostile;
    std::string Role;
    std::string ClassSpec;
    Vector3 Position;
    float Facing = 0.0f;
    uint64 Health = 0;
    uint64 MaxHealth = 0;
    uint32 AlternatePower = 0;
    uint32 MaxAlternatePower = 0;
    float HealthPct = 0.0f;
    bool Alive = false;
    bool Attackable = false;
    bool Selectable = false;
    bool Interactable = false;
    bool InCombat = false;
    bool Flying = false;
    bool ReactAggressive = false;
    ObjectGuid VictimGuid;
    ObjectGuid VehicleGuid;
    std::vector<AuraSnapshot> Auras;
    std::optional<CastSnapshot> Cast;
};

enum class RegionKind : uint8
{
    Hazard,
    Beneficial,
    Cone,
    Line,
    Ring,
    Platform
};

struct SpatialRegion
{
    std::string Id;
    RegionKind Kind = RegionKind::Hazard;
    ObjectGuid SourceGuid;
    uint32 SpellId = 0;
    Vector3 Center;
    float Radius = 0.0f;
    float Facing = 0.0f;
    float HalfAngle = 0.0f;
    float Danger = 0.0f;
    uint64 Generation = 0;
    uint64 ExpiresAtMs = 0;
};

enum class AssignmentKind : uint8
{
    Tank,
    Interrupt,
    Interaction,
    Kite,
    Heal,
    Platform,
    Formation
};

struct AssignmentLease
{
    AssignmentKind Kind = AssignmentKind::Formation;
    std::string Slot;
    ObjectGuid AssigneeGuid;
    ObjectGuid SubjectGuid;
    ObjectGuid BackupGuid;
    uint64 Generation = 0;
    uint64 ExpiresAtMs = 0;
};

struct TargetChannels
{
    ObjectGuid DamageTarget;
    ObjectGuid MechanicTarget;
    ObjectGuid TankAssignment;
    ObjectGuid HealTarget;
    ObjectGuid InteractionTarget;
};

struct RouteView
{
    std::string NodeId;
    std::string Kind;
    std::string Label;
    std::string MechanicProfile;
    std::vector<uint32> AllowedEntries;
    std::vector<Vector3> NavigationHints;
    uint32 HazardSourceEntry = 0;
    uint32 HazardDetectionSpellId = 0;
    float HazardRadius = 0.0f;
    float HazardSafetyMargin = 0.0f;
    float MinimumDistance = 0.0f;
    std::string InteractionAction;
    uint32 InteractionEntry = 0;
    std::vector<uint32> InteractionMenus;
    uint32 InteractionOption = 0;
    std::string CompletionKind;
    uint32 CompletionEntry = 0;
    uint32 CompletionSpellId = 0;
    bool Complete = false;
};

struct Blackboard
{
    Scope CurrentScope;
    uint64 Revision = 0;
    uint64 ObservedAtMs = 0;
    std::string NativeBossState = "unknown";
    std::vector<ActorSnapshot> Players;
    std::vector<ActorSnapshot> Hostiles;
    std::vector<ActorSnapshot> Summons;
    std::vector<ActorSnapshot> Interactables;
    std::vector<SpatialRegion> Regions;
    std::vector<AssignmentLease> Assignments;
    std::map<ObjectGuid, TargetChannels> BotTargets;
    RouteView Route;

    ActorSnapshot const* FindActor(ObjectGuid guid) const
    {
        auto findIn = [guid](std::vector<ActorSnapshot> const& actors) -> ActorSnapshot const*
        {
            auto itr = std::find_if(actors.begin(), actors.end(), [guid](ActorSnapshot const& actor)
            {
                return actor.Guid == guid;
            });
            return itr == actors.end() ? nullptr : &*itr;
        };
        if (ActorSnapshot const* actor = findIn(Players))
            return actor;
        if (ActorSnapshot const* actor = findIn(Hostiles))
            return actor;
        if (ActorSnapshot const* actor = findIn(Summons))
            return actor;
        return findIn(Interactables);
    }
};
}

#endif
