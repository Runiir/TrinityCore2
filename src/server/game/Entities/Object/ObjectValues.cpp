/*
 * This file is part of the TrinityCore Project. See AUTHORS file for Copyright information
 *
 * This program is free software; you can redistribute it and/or modify it
 * under the terms of the GNU General Public License as published by the
 * Free Software Foundation; either version 2 of the License, or (at your
 * option) any later version.
 *
 * This program is distributed in the hope that it will be useful, but WITHOUT
 * ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
 * FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
 * more details.
 *
 * You should have received a copy of the GNU General Public License along
 * with this program. If not, see <http://www.gnu.org/licenses/>.
 */

#include "Object.h"
#include "BattlefieldMgr.h"
#include "Battleground.h"
#include "CellImpl.h"
#include "Chat.h"
#include "CinematicMgr.h"
#include "CombatLogPackets.h"
#include "Common.h"
#include "Creature.h"
#include "DBCStores.h"
#include "G3DPosition.hpp"
#include "GameTime.h"
#include "GridNotifiers.h"
#include "GridNotifiersImpl.h"
#include "Group.h"
#include "Item.h"
#include "Log.h"
#include "MapManager.h"
#include "MiscPackets.h"
#include "MovementPacketBuilder.h"
#include "ObjectAccessor.h"
#include "ObjectMgr.h"
#include "OutdoorPvPMgr.h"
#include "PhasingHandler.h"
#include "PathGenerator.h"
#include "Player.h"
#include "ReputationMgr.h"
#include "SpellAuraEffects.h"
#include "SpellDefines.h"
#include "SpellMgr.h"
#include "StringConvert.h"
#include "TemporarySummon.h"
#include "Totem.h"
#include "Transport.h"
#include "Unit.h"
#include "UpdateData.h"
#include "UpdateFieldFlags.h"
#include "UpdateMask.h"
#include "Util.h"
#include "Vehicle.h"
#include "VMapFactory.h"
#include "VMapManager2.h"
#include "WaypointMovementGenerator.h"
#include "World.h"
#include "WorldPacket.h"

constexpr float VisibilityDistances[AsUnderlyingType(VisibilityDistanceType::Max)] =
{
    DEFAULT_VISIBILITY_DISTANCE,
    VISIBILITY_DISTANCE_TINY,
    VISIBILITY_DISTANCE_SMALL,
    VISIBILITY_DISTANCE_LARGE,
    VISIBILITY_DISTANCE_GIGANTIC,
    MAX_VISIBILITY_DISTANCE
};

bool Object::_LoadIntoDataField(std::string const& data, uint32 startOffset, uint32 count)
{
    if (data.empty())
        return false;

    std::vector<std::string_view> tokens = Trinity::Tokenize(data, ' ', false);

    if (tokens.size() != count)
        return false;

    for (uint32 index = 0; index < count; ++index)
    {
        Optional<uint32> val = Trinity::StringTo<uint32>(tokens[index]);
        if (!val)
            return false;
        m_uint32Values[startOffset + index] = *val;
        _changesMask.SetBit(startOffset + index);
    }
    return true;
}

void Object::SetInt32Value(uint16 index, int32 value)
{
    ASSERT(index < m_valuesCount || PrintIndexError(index, true));

    if (m_int32Values[index] != value)
    {
        m_int32Values[index] = value;
        _changesMask.SetBit(index);

        AddToObjectUpdateIfNeeded();
    }
}

void Object::SetUInt32Value(uint16 index, uint32 value)
{
    ASSERT(index < m_valuesCount || PrintIndexError(index, true));

    if (m_uint32Values[index] != value)
    {
        m_uint32Values[index] = value;
        _changesMask.SetBit(index);

        AddToObjectUpdateIfNeeded();
    }
}

void Object::UpdateUInt32Value(uint16 index, uint32 value)
{
    ASSERT(index < m_valuesCount || PrintIndexError(index, true));

    m_uint32Values[index] = value;
    _changesMask.SetBit(index);
}

void Object::SetUInt64Value(uint16 index, uint64 value)
{
    ASSERT(index + 1 < m_valuesCount || PrintIndexError(index, true));
    if (*((uint64*)&(m_uint32Values[index])) != value)
    {
        m_uint32Values[index] = PAIR64_LOPART(value);
        m_uint32Values[index + 1] = PAIR64_HIPART(value);
        _changesMask.SetBit(index);
        _changesMask.SetBit(index + 1);

        AddToObjectUpdateIfNeeded();
    }
}

bool Object::AddGuidValue(uint16 index, ObjectGuid value)
{
    ASSERT(index + 1 < m_valuesCount || PrintIndexError(index, true));
    if (value && !*((ObjectGuid*)&(m_uint32Values[index])))
    {
        *((ObjectGuid*)&(m_uint32Values[index])) = value;
        _changesMask.SetBit(index);
        _changesMask.SetBit(index + 1);

        AddToObjectUpdateIfNeeded();

        return true;
    }

    return false;
}

bool Object::RemoveGuidValue(uint16 index, ObjectGuid value)
{
    ASSERT(index + 1 < m_valuesCount || PrintIndexError(index, true));
    if (value && *((ObjectGuid*)&(m_uint32Values[index])) == value)
    {
        m_uint32Values[index] = 0;
        m_uint32Values[index + 1] = 0;
        _changesMask.SetBit(index);
        _changesMask.SetBit(index + 1);

        AddToObjectUpdateIfNeeded();

        return true;
    }

    return false;
}

void Object::SetFloatValue(uint16 index, float value)
{
    ASSERT(index < m_valuesCount || PrintIndexError(index, true));

    if (m_floatValues[index] != value)
    {
        m_floatValues[index] = value;
        _changesMask.SetBit(index);

        AddToObjectUpdateIfNeeded();
    }
}

void Object::SetByteValue(uint16 index, uint8 offset, uint8 value)
{
    ASSERT(index < m_valuesCount || PrintIndexError(index, true));
    ASSERT(offset < 4);

    if (uint8(m_uint32Values[index] >> (offset * 8)) != value)
    {
        m_uint32Values[index] &= ~uint32(uint32(0xFF) << (offset * 8));
        m_uint32Values[index] |= uint32(uint32(value) << (offset * 8));
        _changesMask.SetBit(index);

        AddToObjectUpdateIfNeeded();
    }
}

void Object::SetUInt16Value(uint16 index, uint8 offset, uint16 value)
{
    ASSERT(index < m_valuesCount || PrintIndexError(index, true));
    ASSERT(offset < 2);

    if (uint16(m_uint32Values[index] >> (offset * 16)) != value)
    {
        m_uint32Values[index] &= ~uint32(uint32(0xFFFF) << (offset * 16));
        m_uint32Values[index] |= uint32(uint32(value) << (offset * 16));
        _changesMask.SetBit(index);

        AddToObjectUpdateIfNeeded();
    }
}

void Object::SetGuidValue(uint16 index, ObjectGuid value)
{
    ASSERT(index + 1 < m_valuesCount || PrintIndexError(index, true));
    if (*((ObjectGuid*)&(m_uint32Values[index])) != value)
    {
        *((ObjectGuid*)&(m_uint32Values[index])) = value;
        _changesMask.SetBit(index);
        _changesMask.SetBit(index + 1);

        AddToObjectUpdateIfNeeded();
    }
}

void Object::SetStatFloatValue(uint16 index, float value)
{
    if (value < 0)
        value = 0.0f;

    SetFloatValue(index, value);
}

void Object::SetStatInt32Value(uint16 index, int32 value)
{
    if (value < 0)
        value = 0;

    SetUInt32Value(index, uint32(value));
}

void Object::ApplyModUInt32Value(uint16 index, int32 val, bool apply)
{
    int32 cur = GetUInt32Value(index);
    cur += (apply ? val : -val);
    if (cur < 0)
        cur = 0;
    SetUInt32Value(index, cur);
}

void Object::ApplyModInt32Value(uint16 index, int32 val, bool apply)
{
    int32 cur = GetInt32Value(index);
    cur += (apply ? val : -val);
    SetInt32Value(index, cur);
}

void Object::ApplyModSignedFloatValue(uint16 index, float  val, bool apply)
{
    float cur = GetFloatValue(index);
    cur += (apply ? val : -val);
    SetFloatValue(index, cur);
}

void Object::ApplyModPositiveFloatValue(uint16 index, float  val, bool apply)
{
    float cur = GetFloatValue(index);
    cur += (apply ? val : -val);
    if (cur < 0)
        cur = 0;
    SetFloatValue(index, cur);
}

void Object::SetFlag(uint16 index, uint32 newFlag)
{
    ASSERT(index < m_valuesCount || PrintIndexError(index, true));
    uint32 oldval = m_uint32Values[index];
    uint32 newval = oldval | newFlag;

    if (oldval != newval)
    {
        m_uint32Values[index] = newval;
        _changesMask.SetBit(index);

        AddToObjectUpdateIfNeeded();
    }
}

void Object::RemoveFlag(uint16 index, uint32 oldFlag)
{
    ASSERT(index < m_valuesCount || PrintIndexError(index, true));

    uint32 oldval = m_uint32Values[index];
    uint32 newval = oldval & ~oldFlag;

    if (oldval != newval)
    {
        m_uint32Values[index] = newval;
        _changesMask.SetBit(index);

        AddToObjectUpdateIfNeeded();
    }
}

void Object::ToggleFlag(uint16 index, uint32 flag)
{
    if (HasFlag(index, flag))
        RemoveFlag(index, flag);
    else
        SetFlag(index, flag);
}

bool Object::HasFlag(uint16 index, uint32 flag) const
{
    ASSERT(index < m_valuesCount || PrintIndexError(index, true));
    return (m_uint32Values[index] & flag) != 0;
}

void Object::ApplyModFlag(uint16 index, uint32 flag, bool apply)
{
    if (apply) SetFlag(index, flag); else RemoveFlag(index, flag);
}

void Object::SetByteFlag(uint16 index, uint8 offset, uint8 newFlag)
{
    ASSERT(index < m_valuesCount || PrintIndexError(index, true));
    ASSERT(offset < 4);

    if (!(uint8(m_uint32Values[index] >> (offset * 8)) & newFlag))
    {
        m_uint32Values[index] |= uint32(uint32(newFlag) << (offset * 8));
        _changesMask.SetBit(index);

        AddToObjectUpdateIfNeeded();
    }
}

void Object::RemoveByteFlag(uint16 index, uint8 offset, uint8 oldFlag)
{
    ASSERT(index < m_valuesCount || PrintIndexError(index, true));
    ASSERT(offset < 4);

    if (uint8(m_uint32Values[index] >> (offset * 8)) & oldFlag)
    {
        m_uint32Values[index] &= ~uint32(uint32(oldFlag) << (offset * 8));
        _changesMask.SetBit(index);

        AddToObjectUpdateIfNeeded();
    }
}

void Object::ToggleByteFlag(uint16 index, uint8 offset, uint8 flag)
{
    if (HasByteFlag(index, offset, flag))
        RemoveByteFlag(index, offset, flag);
    else
        SetByteFlag(index, offset, flag);
}

bool Object::HasByteFlag(uint16 index, uint8 offset, uint8 flag) const
{
    ASSERT(index < m_valuesCount || PrintIndexError(index, false));
    ASSERT(offset < 4);
    return (((uint8*)&m_uint32Values[index])[offset] & flag) != 0;
}

void Object::ApplyModByteFlag(uint16 index, uint8 offset, uint8 flag, bool apply)
{
    if (apply) SetByteFlag(index, offset, flag); else RemoveByteFlag(index, offset, flag);
}

void Object::SetFlag64(uint16 index, uint64 newFlag)
{
    uint64 oldval = GetUInt64Value(index);
    uint64 newval = oldval | newFlag;
    SetUInt64Value(index, newval);
}

void Object::RemoveFlag64(uint16 index, uint64 oldFlag)
{
    uint64 oldval = GetUInt64Value(index);
    uint64 newval = oldval & ~oldFlag;
    SetUInt64Value(index, newval);
}

void Object::ToggleFlag64(uint16 index, uint64 flag)
{
    if (HasFlag64(index, flag))
        RemoveFlag64(index, flag);
    else
        SetFlag64(index, flag);
}

bool Object::HasFlag64(uint16 index, uint64 flag) const
{
    ASSERT(index < m_valuesCount || PrintIndexError(index, false));
    return (GetUInt64Value(index) & flag) != 0;
}

void Object::ApplyModFlag64(uint16 index, uint64 flag, bool apply)
{
    if (apply) SetFlag64(index, flag); else RemoveFlag64(index, flag);
}

bool Object::PrintIndexError(uint32 index, bool set) const
{
    TC_LOG_ERROR("misc", "Attempt to %s non-existing value field: %u (count: %u) for object typeid: %u type mask: %u", (set ? "set value to" : "get value from"), index, m_valuesCount, GetTypeId(), m_objectType);

    // ASSERT must fail after function call
    return false;
}

WorldObject::WorldObject(bool isWorldObject) : Object(), WorldLocation(), LastUsedScriptID(0),
m_movementInfo(), m_name(""), m_isActive(false), m_isFarVisible(false), m_isWorldObject(isWorldObject), m_zoneScript(nullptr),
m_transport(nullptr), m_zoneId(0), m_areaId(0), m_staticFloorZ(VMAP_INVALID_HEIGHT), m_outdoors(true), m_liquidStatus(LIQUID_MAP_NO_WATER),
m_wmoGroupID(0), m_currMap(nullptr), m_InstanceId(0), _dbPhase(0), m_notifyflags(0), _heartbeatTimer(HEARTBEAT_INTERVAL),
m_aiAnimKitId(0), m_movementAnimKitId(0), m_meleeAnimKitId(0)
{
    m_serverSideVisibility.SetValue(SERVERSIDE_VISIBILITY_GHOST, GHOST_VISIBILITY_ALIVE | GHOST_VISIBILITY_GHOST);
    m_serverSideVisibilityDetect.SetValue(SERVERSIDE_VISIBILITY_GHOST, GHOST_VISIBILITY_ALIVE);
}

void WorldObject::SetWorldObject(bool on)
{
    if (!IsInWorld())
        return;

    GetMap()->AddObjectToSwitchList(this, on);
}

bool WorldObject::IsWorldObject() const
{
    if (m_isWorldObject)
        return true;

    if (ToCreature() && ToCreature()->m_isTempWorldObject)
        return true;

    return false;
}

void WorldObject::setActive(bool on)
{
    if (m_isActive == on)
        return;

    if (GetTypeId() == TYPEID_PLAYER)
        return;

    m_isActive = on;

    if (on && !IsInWorld())
        return;

    Map* map = FindMap();
    if (!map)
        return;

    if (on)
        map->AddToActive(this);
    else
        map->RemoveFromActive(this);
}

void WorldObject::SetFarVisible(bool on)
{
    if (GetTypeId() == TYPEID_PLAYER)
        return;

    m_isFarVisible = on;
}

void WorldObject::SetVisibilityDistanceOverride(VisibilityDistanceType type)
{
    ASSERT(type < VisibilityDistanceType::Max);
    if (GetTypeId() == TYPEID_PLAYER)
        return;

    m_visibilityDistanceOverride = VisibilityDistances[AsUnderlyingType(type)];
}

void WorldObject::CleanupsBeforeDelete(bool /*finalCleanup*/)
{
    if (IsInWorld())
        RemoveFromWorld();

    if (TransportBase* transport = GetTransport())
        transport->RemovePassenger(this);

    m_Events.KillAllEvents(false);                      // non-delatable (currently cast spells) will not deleted now but it will deleted at call in Map::RemoveAllObjectsInRemoveList
}

void WorldObject::_Create(ObjectGuid::LowType guidlow, HighGuid guidhigh)
{
    Object::_Create(guidlow, 0, guidhigh);
}

void WorldObject::UpdatePositionData()
{
    PositionFullTerrainStatus data;
    GetMap()->GetFullTerrainStatusForPosition(GetPhaseShift(), GetPositionX(), GetPositionY(), GetPositionZ(), data, map_liquidHeaderTypeFlags::AllLiquids, GetCollisionHeight());
    ProcessPositionDataChanged(data);
}

void WorldObject::ProcessPositionDataChanged(PositionFullTerrainStatus const& data)
{
    m_zoneId = m_areaId = data.areaId;
    if (AreaTableEntry const* area = sAreaTableStore.LookupEntry(m_areaId))
        if (area->ParentAreaID && area->GetFlags().HasFlag(AreaFlags::IsSubzone))
            m_zoneId = area->ParentAreaID;
    m_outdoors = data.outdoors;
    m_staticFloorZ = data.floorZ;
    m_liquidStatus = data.liquidStatus;
    m_wmoGroupID = data.areaInfo.has_value() ? data.areaInfo->groupId : 0;
}

void WorldObject::AddToWorld()
{
    Object::AddToWorld();
    GetMap()->GetZoneAndAreaId(GetPhaseShift(), m_zoneId, m_areaId, GetPositionX(), GetPositionY(), GetPositionZ());
}
void WorldObject::RemoveFromWorld()
{
    if (!IsInWorld())
        return;

    UpdateObjectVisibilityOnDestroy();

    Object::RemoveFromWorld();
}
