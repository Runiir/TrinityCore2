#ifndef TRINITY_BOT_VALIDATION_ROUTE_NATIVE_CONTRACT_H
#define TRINITY_BOT_VALIDATION_ROUTE_NATIVE_CONTRACT_H

// Typed, fail-closed route contracts for native interactions, observed
// completions and transports. Pure data + parsing: no server dependencies.
//
// A contract only declares what a player would do (use an object, pick a
// gossip option, click a vehicle, stand in an area trigger, step onto an
// elevator) and which native postcondition proves it worked. Execution always
// goes through the player's own opcode handlers; completion is observed, never
// written.

#include "Bots/BotValidationRouteNativeJson.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <initializer_list>
#include <string>
#include <string_view>
#include <vector>

namespace BotValidationRouteNative
{
using Json = BotValidationRouteNativeJson::Value;

struct ParseError
{
    enum class Code : std::uint8_t { None, UnknownField, Invalid };

    Code Kind = Code::None;
    std::string Detail;

    explicit operator bool() const { return Kind != Code::None; }

    static ParseError Unknown(std::string_view field)
    {
        return { Code::UnknownField, std::string(field) };
    }

    static ParseError Invalid(std::string_view detail)
    {
        return { Code::Invalid, std::string(detail) };
    }
};

inline bool KnownField(std::string_view key, std::initializer_list<std::string_view> allowed)
{
    return std::find(allowed.begin(), allowed.end(), key) != allowed.end();
}

// ---------------------------------------------------------------------------
// Interaction
// ---------------------------------------------------------------------------
enum class InteractionAction : std::uint8_t
{
    None,
    GameObjectUse,
    GossipSelect,
    GossipSelectSequence,
    SpellClick,
    VehicleEnter,
    AreaTrigger
};

enum class TargetType : std::uint8_t { None, Any, GameObject, Creature };

struct InteractionContract
{
    bool Declared = false;
    InteractionAction Action = InteractionAction::None;
    std::string ActionName;
    TargetType Target = TargetType::None;
    std::uint32_t Entry = 0;
    std::uint64_t SpawnId = 0;
    std::vector<std::uint32_t> Menus;
    std::uint32_t Option = 0;
    // Vehicle seat index; -1 lets the native spellclick choose.
    std::int32_t Seat = -1;
    std::uint32_t AreaTriggerId = 0;
    // Owner selection. When none is declared the lowest living GUID owns the
    // interaction (the historical behaviour, kept for neutrality).
    std::string OwnerRole;
    std::uint32_t OwnerRosterSlot = 0;
    std::uint32_t BackupRosterSlot = 0;
    std::uint32_t TimeoutMs = 0;
    std::uint32_t MaxAttempts = 0;
    std::uint32_t RetryIntervalMs = 0;
    bool Gather = false;
    float GatherRadiusYards = 0.0f;
    // 0 means the native INTERACTION_DISTANCE.
    float RangeYards = 0.0f;

    bool IsGossip() const
    {
        return Action == InteractionAction::GossipSelect
            || Action == InteractionAction::GossipSelectSequence;
    }

    bool LegacyOwner() const { return OwnerRole.empty() && !OwnerRosterSlot; }
};

inline InteractionAction InteractionActionFromName(std::string_view name)
{
    if (name == "gameobject_use") return InteractionAction::GameObjectUse;
    if (name == "gossip_select") return InteractionAction::GossipSelect;
    if (name == "gossip_select_sequence") return InteractionAction::GossipSelectSequence;
    if (name == "spellclick") return InteractionAction::SpellClick;
    if (name == "vehicle_enter") return InteractionAction::VehicleEnter;
    if (name == "area_trigger") return InteractionAction::AreaTrigger;
    return InteractionAction::None;
}

inline ParseError ParseInteraction(Json const& object, InteractionContract& out)
{
    out = InteractionContract();
    if (!object.IsObject())
        return ParseError::Invalid("not_object");
    for (auto const& [key, value] : object.Members)
        if (!KnownField(key, { "action", "entry", "spawn_id", "target_type",
                "menu", "menus", "option", "seat", "area_trigger_id",
                "owner_role", "owner_roster_slot", "backup_roster_slot",
                "timeout_ms", "max_attempts", "retry_interval_ms", "gather",
                "gather_radius_yards", "range_yards" }))
            return ParseError::Unknown(key);

    namespace J = BotValidationRouteNativeJson;
    std::uint64_t entry = 0, spawnId = 0, menu = 0, option = 0, trigger = 0;
    std::uint64_t ownerSlot = 0, backupSlot = 0, timeout = 0, attempts = 0, retry = 0;
    std::int64_t seat = -1;
    std::string targetType;
    if (!J::ReadString(object, "action", out.ActionName))
        return ParseError::Invalid("action_type");
    if (!J::ReadUnsigned(object, "entry", entry, 0xFFFFFFFFull)
        || !J::ReadUnsigned(object, "spawn_id", spawnId, 0xFFFFFFFFFFFFull)
        || !J::ReadUnsigned(object, "menu", menu, 0xFFFFFFFFull)
        || !J::ReadUnsigned(object, "option", option, 0xFFFFFFFFull)
        || !J::ReadUnsigned(object, "area_trigger_id", trigger, 0xFFFFFFFFull)
        || !J::ReadUnsigned(object, "owner_roster_slot", ownerSlot, 40)
        || !J::ReadUnsigned(object, "backup_roster_slot", backupSlot, 40)
        || !J::ReadUnsigned(object, "timeout_ms", timeout, 600000)
        || !J::ReadUnsigned(object, "max_attempts", attempts, 100)
        || !J::ReadUnsigned(object, "retry_interval_ms", retry, 60000)
        || !J::ReadSigned(object, "seat", seat, -1, 7)
        || !J::ReadString(object, "target_type", targetType)
        || !J::ReadString(object, "owner_role", out.OwnerRole)
        || !J::ReadBool(object, "gather", out.Gather)
        || !J::ReadFloat(object, "gather_radius_yards", out.GatherRadiusYards)
        || !J::ReadFloat(object, "range_yards", out.RangeYards))
        return ParseError::Invalid("field_type_or_range");

    if (Json const* menus = object.Find("menus"))
    {
        if (!menus->IsArray() || menus->Items.empty())
            return ParseError::Invalid("menus_shape");
        for (Json const& item : menus->Items)
        {
            if (!item.IsNumber() || !item.Integral || item.Negative
                || item.Number < 1.0 || item.Number > 4294967295.0)
                return ParseError::Invalid("menus_shape");
            std::uint32_t const value = std::uint32_t(item.Number);
            if (std::find(out.Menus.begin(), out.Menus.end(), value) != out.Menus.end())
                return ParseError::Invalid("menus_duplicate");
            out.Menus.push_back(value);
        }
    }
    if (object.Find("menu"))
    {
        if (!out.Menus.empty())
            return ParseError::Invalid("gossip_menu_ambiguous");
        if (!menu)
            return ParseError::Invalid("menus_shape");
        out.Menus.push_back(std::uint32_t(menu));
    }

    out.Action = InteractionActionFromName(out.ActionName);
    out.Entry = std::uint32_t(entry);
    out.SpawnId = spawnId;
    out.Option = std::uint32_t(option);
    out.Seat = std::int32_t(seat);
    out.AreaTriggerId = std::uint32_t(trigger);
    out.OwnerRosterSlot = std::uint32_t(ownerSlot);
    out.BackupRosterSlot = std::uint32_t(backupSlot);
    out.TimeoutMs = std::uint32_t(timeout);
    out.MaxAttempts = std::uint32_t(attempts);
    out.RetryIntervalMs = std::uint32_t(retry);

    if (out.Action == InteractionAction::None)
        return ParseError::Invalid("action_unknown");

    bool const hasTarget = out.Entry || out.SpawnId;
    bool const areaTrigger = out.Action == InteractionAction::AreaTrigger;
    if (areaTrigger)
    {
        if (!out.AreaTriggerId || hasTarget || !targetType.empty())
            return ParseError::Invalid("area_trigger_shape");
        out.Target = TargetType::None;
    }
    else
    {
        if (!hasTarget)
            return ParseError::Invalid("target_missing");
        if (out.AreaTriggerId)
            return ParseError::Invalid("area_trigger_unexpected");
        TargetType const implied = out.Action == InteractionAction::GameObjectUse
            ? TargetType::GameObject
            : (out.Action == InteractionAction::SpellClick
                || out.Action == InteractionAction::VehicleEnter)
                ? TargetType::Creature : TargetType::Any;
        if (targetType.empty())
            out.Target = implied;
        else if (targetType == "gameobject")
            out.Target = TargetType::GameObject;
        else if (targetType == "creature")
            out.Target = TargetType::Creature;
        else
            return ParseError::Invalid("target_type_unknown");
        if (implied != TargetType::Any && out.Target != implied)
            return ParseError::Invalid("target_type_conflicts_with_action");
    }

    if (out.IsGossip())
    {
        if (out.Menus.empty())
            return ParseError::Invalid("gossip_menu_missing");
    }
    else if (!out.Menus.empty() || object.Find("option"))
        return ParseError::Invalid("menu_unexpected");

    if (out.Action != InteractionAction::VehicleEnter && object.Find("seat"))
        return ParseError::Invalid("seat_unexpected");

    if (!out.OwnerRole.empty() && out.OwnerRole != "tank"
        && out.OwnerRole != "healer" && out.OwnerRole != "dps")
        return ParseError::Invalid("owner_role_unknown");
    if (object.Find("owner_roster_slot") && !out.OwnerRosterSlot)
        return ParseError::Invalid("owner_roster_slot_invalid");
    if (!out.OwnerRole.empty() && out.OwnerRosterSlot)
        return ParseError::Invalid("owner_ambiguous");
    if (object.Find("backup_roster_slot"))
    {
        if (!out.BackupRosterSlot)
            return ParseError::Invalid("backup_roster_slot_invalid");
        if (out.LegacyOwner())
            return ParseError::Invalid("backup_without_owner");
        if (out.BackupRosterSlot == out.OwnerRosterSlot)
            return ParseError::Invalid("backup_equals_owner");
    }
    if (out.Gather)
    {
        if (!(out.GatherRadiusYards > 0.0f && out.GatherRadiusYards <= 60.0f))
            return ParseError::Invalid("gather_radius_invalid");
    }
    else if (object.Find("gather_radius_yards"))
        return ParseError::Invalid("gather_radius_without_gather");
    if (object.Find("range_yards")
        && !(out.RangeYards > 0.0f && out.RangeYards <= 30.0f))
        return ParseError::Invalid("range_invalid");

    out.Declared = true;
    return {};
}

// ---------------------------------------------------------------------------
// Completion
// ---------------------------------------------------------------------------
enum class CompletionKind : std::uint8_t
{
    None,
    GameObjectSelectable,
    GameObjectDespawned,
    BossSummoned,
    CreatureSummoned,
    AuraPresent,
    CreatureAggressiveWithVictim,
    CreatureGroundedAggressiveOrEngaged,
    InstanceBossState,
    OnTransport,
    VehicleSeated,
    TransportAtStop,
    AnyOf,
    AllOf
};

enum class MemberScope : std::uint8_t { All, Any, Owner };

// Matches EncounterState in Instances/InstanceScript.h.
inline bool BossStateFromName(std::string_view name, std::uint32_t& state)
{
    static constexpr std::string_view Names[] =
        { "not_started", "in_progress", "fail", "done", "special", "to_be_decided" };
    for (std::uint32_t i = 0; i < 6; ++i)
        if (Names[i] == name)
        {
            state = i;
            return true;
        }
    return false;
}

inline CompletionKind CompletionKindFromName(std::string_view name)
{
    if (name == "gameobject_selectable") return CompletionKind::GameObjectSelectable;
    if (name == "gameobject_despawned") return CompletionKind::GameObjectDespawned;
    if (name == "boss_summoned") return CompletionKind::BossSummoned;
    if (name == "creature_summoned") return CompletionKind::CreatureSummoned;
    if (name == "aura_present") return CompletionKind::AuraPresent;
    if (name == "creature_aggressive_with_victim") return CompletionKind::CreatureAggressiveWithVictim;
    if (name == "creature_grounded_aggressive_or_engaged") return CompletionKind::CreatureGroundedAggressiveOrEngaged;
    if (name == "instance_boss_state") return CompletionKind::InstanceBossState;
    if (name == "on_transport") return CompletionKind::OnTransport;
    if (name == "vehicle_seated") return CompletionKind::VehicleSeated;
    if (name == "transport_at_stop") return CompletionKind::TransportAtStop;
    if (name == "any_of") return CompletionKind::AnyOf;
    if (name == "all_of") return CompletionKind::AllOf;
    return CompletionKind::None;
}

struct CompletionContract
{
    bool Declared = false;
    CompletionKind Kind = CompletionKind::None;
    std::string KindName;
    std::uint32_t Entry = 0;
    std::uint64_t SpawnId = 0;
    std::uint32_t SpellId = 0;
    std::int32_t BossIndex = -1;
    std::uint32_t BossState = 0;
    std::uint32_t TransportEntry = 0;
    std::uint64_t TransportSpawnId = 0;
    std::int32_t StopFrame = -1;
    std::uint32_t VehicleEntry = 0;
    std::int32_t Seat = -1;
    MemberScope Scope = MemberScope::All;
    // gameobject_despawned only completes after the object was observed
    // spawned in the same route scope, so an absent (never spawned or out of
    // range) object cannot satisfy it vacuously.
    bool RequireObservedPresent = true;
    std::vector<CompletionContract> Children;

    bool UsesOwnerScope() const
    {
        if (Scope == MemberScope::Owner)
            return true;
        return std::any_of(Children.begin(), Children.end(),
            [](CompletionContract const& child) { return child.UsesOwnerScope(); });
    }
};

inline ParseError ParseCompletion(Json const& object, CompletionContract& out, int depth = 0)
{
    out = CompletionContract();
    if (!object.IsObject())
        return ParseError::Invalid("not_object");
    for (auto const& [key, value] : object.Members)
        if (!KnownField(key, { "kind", "entry", "spawn_id", "spell_id",
                "boss_index", "boss_state", "transport_entry",
                "transport_spawn_id", "stop_frame", "vehicle_entry", "seat",
                "scope", "contracts", "require_observed_present" }))
            return ParseError::Unknown(key);

    namespace J = BotValidationRouteNativeJson;
    std::uint64_t entry = 0, spawnId = 0, spell = 0, transportEntry = 0;
    std::uint64_t transportSpawn = 0, vehicleEntry = 0;
    std::int64_t bossIndex = -1, stopFrame = -1, seat = -1;
    std::string bossState, scope;
    if (!J::ReadString(object, "kind", out.KindName)
        || !J::ReadUnsigned(object, "entry", entry, 0xFFFFFFFFull)
        || !J::ReadUnsigned(object, "spawn_id", spawnId, 0xFFFFFFFFFFFFull)
        || !J::ReadUnsigned(object, "spell_id", spell, 0xFFFFFFFFull)
        || !J::ReadSigned(object, "boss_index", bossIndex, 0, 63)
        || !J::ReadString(object, "boss_state", bossState)
        || !J::ReadUnsigned(object, "transport_entry", transportEntry, 0xFFFFFFFFull)
        || !J::ReadUnsigned(object, "transport_spawn_id", transportSpawn, 0xFFFFFFFFFFFFull)
        || !J::ReadSigned(object, "stop_frame", stopFrame, 0, 8)
        || !J::ReadUnsigned(object, "vehicle_entry", vehicleEntry, 0xFFFFFFFFull)
        || !J::ReadSigned(object, "seat", seat, -1, 7)
        || !J::ReadString(object, "scope", scope)
        || !J::ReadBool(object, "require_observed_present", out.RequireObservedPresent))
        return ParseError::Invalid("field_type_or_range");

    out.Kind = CompletionKindFromName(out.KindName);
    out.Entry = std::uint32_t(entry);
    out.SpawnId = spawnId;
    out.SpellId = std::uint32_t(spell);
    out.BossIndex = std::int32_t(bossIndex);
    out.TransportEntry = std::uint32_t(transportEntry);
    out.TransportSpawnId = transportSpawn;
    out.StopFrame = std::int32_t(stopFrame);
    out.VehicleEntry = std::uint32_t(vehicleEntry);
    out.Seat = std::int32_t(seat);
    if (out.Kind == CompletionKind::None)
        return ParseError::Invalid("kind_unknown:" + out.KindName);

    // Each kind accepts exactly its own fields.
    auto onlyFields = [&object](std::initializer_list<std::string_view> allowed)
        -> ParseError
    {
        for (auto const& [key, value] : object.Members)
            if (key != "kind" && !KnownField(key, allowed))
                return ParseError::Invalid("field_unexpected:" + key);
        return {};
    };
    bool const objectTarget = out.Entry || out.SpawnId;
    switch (out.Kind)
    {
        case CompletionKind::GameObjectSelectable:
            if (ParseError error = onlyFields({ "entry", "spawn_id" }))
                return error;
            if (!objectTarget)
                return ParseError::Invalid("target_missing");
            break;
        case CompletionKind::GameObjectDespawned:
            if (ParseError error = onlyFields({ "entry", "spawn_id", "require_observed_present" }))
                return error;
            if (!objectTarget)
                return ParseError::Invalid("target_missing");
            break;
        case CompletionKind::BossSummoned:
        case CompletionKind::CreatureSummoned:
        case CompletionKind::CreatureAggressiveWithVictim:
        case CompletionKind::CreatureGroundedAggressiveOrEngaged:
            if (ParseError error = onlyFields({ "entry" }))
                return error;
            if (!out.Entry)
                return ParseError::Invalid("entry_missing");
            break;
        case CompletionKind::AuraPresent:
            if (ParseError error = onlyFields({ "entry", "spell_id" }))
                return error;
            if (!out.Entry || !out.SpellId)
                return ParseError::Invalid("aura_shape");
            break;
        case CompletionKind::InstanceBossState:
            if (ParseError error = onlyFields({ "boss_index", "boss_state" }))
                return error;
            if (out.BossIndex < 0 || !BossStateFromName(bossState, out.BossState))
                return ParseError::Invalid("boss_state_shape");
            break;
        case CompletionKind::OnTransport:
            if (ParseError error = onlyFields({ "transport_entry", "transport_spawn_id", "scope" }))
                return error;
            if (!out.TransportEntry && !out.TransportSpawnId)
                return ParseError::Invalid("transport_missing");
            break;
        case CompletionKind::VehicleSeated:
            if (ParseError error = onlyFields({ "vehicle_entry", "seat", "scope" }))
                return error;
            if (!out.VehicleEntry)
                return ParseError::Invalid("vehicle_missing");
            break;
        case CompletionKind::TransportAtStop:
            if (ParseError error = onlyFields({ "transport_entry", "transport_spawn_id", "stop_frame" }))
                return error;
            if ((!out.TransportEntry && !out.TransportSpawnId) || out.StopFrame < 0)
                return ParseError::Invalid("transport_stop_shape");
            break;
        case CompletionKind::AnyOf:
        case CompletionKind::AllOf:
        {
            if (ParseError error = onlyFields({ "contracts" }))
                return error;
            if (depth >= 2)
                return ParseError::Invalid("composite_too_deep");
            Json const* children = object.Find("contracts");
            if (!children || !children->IsArray() || children->Items.empty()
                || children->Items.size() > 8)
                return ParseError::Invalid("composite_shape");
            for (Json const& item : children->Items)
            {
                CompletionContract child;
                if (ParseError error = ParseCompletion(item, child, depth + 1))
                    return error.Kind == ParseError::Code::UnknownField
                        ? error : ParseError::Invalid("child:" + error.Detail);
                out.Children.push_back(std::move(child));
            }
            break;
        }
        case CompletionKind::None:
            break;
    }

    if (!scope.empty())
    {
        if (scope == "all")
            out.Scope = MemberScope::All;
        else if (scope == "any")
            out.Scope = MemberScope::Any;
        else if (scope == "owner")
            out.Scope = MemberScope::Owner;
        else
            return ParseError::Invalid("scope_unknown");
    }
    out.Declared = true;
    return {};
}

// ---------------------------------------------------------------------------
// Transport (elevators and other GAMEOBJECT_TYPE_TRANSPORT platforms)
// ---------------------------------------------------------------------------
struct Point3
{
    float X = 0.0f;
    float Y = 0.0f;
    float Z = 0.0f;
    bool Valid = false;
};

struct TransportContract
{
    bool Declared = false;
    std::uint32_t Entry = 0;
    std::uint64_t SpawnId = 0;
    // Boarding readiness: either a native stop frame (GoState 25 + frame and
    // arrival time reached) or the platform's world Z (cycling elevators).
    std::int32_t BoardStopFrame = -1;
    bool HasBoardLevel = false;
    float BoardTransportZ = 0.0f;
    // Optional ride destination. Without it, being aboard completes the node.
    std::int32_t ExitStopFrame = -1;
    bool HasExitLevel = false;
    float ExitTransportZ = 0.0f;
    float LevelToleranceYards = 0.75f;
    Point3 WaitPoint;
    Point3 BoardPoint;
    // Optional point on the platform, over static ground at the exit level,
    // to stand on before leaving when the boarding spot is not over ground.
    Point3 DisembarkPoint;
    Point3 ExitPoint;
    float ArrivalToleranceYards = 1.5f;
    float FootprintMarginYards = 0.5f;
    std::uint32_t TimeoutMs = 0;

    bool HasExit() const { return ExitStopFrame >= 0 || HasExitLevel; }
};

inline bool ReadPoint(Json const& object, std::string_view key, Point3& out)
{
    Json const* value = object.Find(key);
    if (!value)
        return true;
    if (!value->IsArray() || value->Items.size() != 3)
        return false;
    float coordinates[3] = {};
    for (std::size_t i = 0; i < 3; ++i)
    {
        if (!value->Items[i].IsNumber() || !std::isfinite(value->Items[i].Number))
            return false;
        coordinates[i] = float(value->Items[i].Number);
    }
    out = { coordinates[0], coordinates[1], coordinates[2], true };
    return true;
}

inline ParseError ParseTransport(Json const& object, TransportContract& out)
{
    out = TransportContract();
    if (!object.IsObject())
        return ParseError::Invalid("not_object");
    for (auto const& [key, value] : object.Members)
        if (!KnownField(key, { "entry", "spawn_id", "board_stop_frame",
                "board_transport_z", "exit_stop_frame", "exit_transport_z",
                "level_tolerance_yards", "wait_point", "board_point",
                "disembark_point", "exit_point", "arrival_tolerance_yards",
                "footprint_margin_yards", "timeout_ms" }))
            return ParseError::Unknown(key);

    namespace J = BotValidationRouteNativeJson;
    std::uint64_t entry = 0, spawnId = 0, timeout = 0;
    std::int64_t boardFrame = -1, exitFrame = -1;
    if (!J::ReadUnsigned(object, "entry", entry, 0xFFFFFFFFull)
        || !J::ReadUnsigned(object, "spawn_id", spawnId, 0xFFFFFFFFFFFFull)
        || !J::ReadUnsigned(object, "timeout_ms", timeout, 1800000)
        || !J::ReadSigned(object, "board_stop_frame", boardFrame, 0, 8)
        || !J::ReadSigned(object, "exit_stop_frame", exitFrame, 0, 8)
        || !J::ReadFloat(object, "board_transport_z", out.BoardTransportZ)
        || !J::ReadFloat(object, "exit_transport_z", out.ExitTransportZ)
        || !J::ReadFloat(object, "level_tolerance_yards", out.LevelToleranceYards)
        || !J::ReadFloat(object, "arrival_tolerance_yards", out.ArrivalToleranceYards)
        || !J::ReadFloat(object, "footprint_margin_yards", out.FootprintMarginYards)
        || !ReadPoint(object, "wait_point", out.WaitPoint)
        || !ReadPoint(object, "board_point", out.BoardPoint)
        || !ReadPoint(object, "disembark_point", out.DisembarkPoint)
        || !ReadPoint(object, "exit_point", out.ExitPoint))
        return ParseError::Invalid("field_type_or_range");

    out.Entry = std::uint32_t(entry);
    out.SpawnId = spawnId;
    out.TimeoutMs = std::uint32_t(timeout);
    out.BoardStopFrame = std::int32_t(boardFrame);
    out.ExitStopFrame = std::int32_t(exitFrame);
    out.HasBoardLevel = object.Find("board_transport_z") != nullptr;
    out.HasExitLevel = object.Find("exit_transport_z") != nullptr;

    if (!out.Entry && !out.SpawnId)
        return ParseError::Invalid("transport_missing");
    if ((out.BoardStopFrame >= 0) == out.HasBoardLevel)
        return ParseError::Invalid("board_readiness_ambiguous");
    if (out.ExitStopFrame >= 0 && out.HasExitLevel)
        return ParseError::Invalid("exit_readiness_ambiguous");
    if (!out.BoardPoint.Valid)
        return ParseError::Invalid("board_point_missing");
    if (out.HasExit() != out.ExitPoint.Valid
        || (out.DisembarkPoint.Valid && !out.HasExit()))
        return ParseError::Invalid("exit_shape");
    if (!(out.LevelToleranceYards > 0.0f && out.LevelToleranceYards <= 10.0f)
        || !(out.ArrivalToleranceYards > 0.0f && out.ArrivalToleranceYards <= 10.0f)
        || !(out.FootprintMarginYards >= 0.0f && out.FootprintMarginYards <= 5.0f))
        return ParseError::Invalid("tolerance_invalid");
    out.Declared = true;
    return {};
}

inline ParseError ParseObjectText(std::string_view text, Json& out)
{
    std::string error;
    if (!BotValidationRouteNativeJson::Parse(text, out, error))
        return ParseError::Invalid(error);
    if (!out.IsObject())
        return ParseError::Invalid("not_object");
    return {};
}

// Node-level shape: which route kinds may carry which contracts.
inline ParseError ValidateNodeShape(std::string_view kind,
    InteractionContract const& interaction, CompletionContract const& completion,
    TransportContract const& transport)
{
    if (transport.Declared != (kind == "transport"))
        return ParseError::Invalid(transport.Declared
            ? "transport_contract_requires_transport_kind"
            : "transport_kind_requires_transport_contract");
    if (interaction.Declared && kind != "interaction")
        return ParseError::Invalid("interaction_contract_requires_interaction_kind");
    if (kind == "interaction" && !interaction.Declared && !completion.Declared)
        return ParseError::Invalid("interaction_kind_requires_contract");
    if (completion.Declared && completion.UsesOwnerScope() && !interaction.Declared)
        return ParseError::Invalid("owner_scope_requires_interaction");
    return {};
}
}

#endif
