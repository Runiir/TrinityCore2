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

Object::Object()
{
    m_objectTypeId      = TYPEID_OBJECT;
    m_objectType        = TYPEMASK_OBJECT;
    m_updateFlag.Clear();

    m_uint32Values      = nullptr;
    m_valuesCount       = 0;
    _fieldNotifyFlags   = UF_FLAG_DYNAMIC;

    m_inWorld           = false;
    m_isNewObject       = false;
    m_isDestroyedObject = false;
    m_objectUpdated     = false;
}

WorldObject::~WorldObject()
{
    // this may happen because there are many !create/delete
    if (IsWorldObject() && m_currMap)
    {
        if (GetTypeId() == TYPEID_CORPSE)
        {
            TC_LOG_FATAL("misc", "WorldObject::~WorldObject Corpse Type: %d (%s) deleted but still in map!!",
                ToCorpse()->GetType(), GetGUID().ToString().c_str());
            ABORT();
        }
        ResetMap();
    }
}

void WorldObject::Update(uint32 diff)
{
    m_Events.Update(diff);

    _heartbeatTimer -= Milliseconds(diff);
    while (_heartbeatTimer <= 0ms)
    {
        _heartbeatTimer += HEARTBEAT_INTERVAL;
        Heartbeat();
    }
}

Object::~Object()
{
    if (IsInWorld())
    {
        TC_LOG_FATAL("misc", "Object::~Object %s deleted but still in world!!", GetGUID().ToString().c_str());
        if (isType(TYPEMASK_ITEM))
            TC_LOG_FATAL("misc", "Item slot %u", ((Item*)this)->GetSlot());
        ABORT();
    }

    if (m_objectUpdated)
    {
        TC_LOG_FATAL("misc", "Object::~Object %s deleted but still in update list!!", GetGUID().ToString().c_str());
        ABORT();
    }

    delete [] m_uint32Values;
    m_uint32Values = nullptr;
}

void Object::_InitValues()
{
    m_uint32Values = new uint32[m_valuesCount];
    memset(m_uint32Values, 0, m_valuesCount*sizeof(uint32));

    _changesMask.SetCount(m_valuesCount);

    m_objectUpdated = false;
}

void Object::_Create(ObjectGuid::LowType guidlow, uint32 entry, HighGuid guidhigh)
{
    if (!m_uint32Values) _InitValues();

    ObjectGuid guid(guidhigh, entry, guidlow);
    SetGuidValue(OBJECT_FIELD_GUID, guid);
    SetUInt16Value(OBJECT_FIELD_TYPE, 0, m_objectType);
    m_PackGUID.Set(guid);
}

std::string Object::_ConcatFields(uint16 startIndex, uint16 size) const
{
    std::ostringstream ss;
    for (uint16 index = 0; index < size; ++index)
        ss << GetUInt32Value(index + startIndex) << ' ';
    return ss.str();
}

void Object::AddToWorld()
{
    if (m_inWorld)
        return;

    ASSERT(m_uint32Values);

    m_inWorld = true;

    // synchronize values mirror with values array (changes will send in updatecreate opcode any way
    ASSERT(!m_objectUpdated);
    ClearUpdateMask(false);
}

void Object::RemoveFromWorld()
{
    if (!m_inWorld)
        return;

    m_inWorld = false;

    // if we remove from world then sending changes not required
    ClearUpdateMask(true);
}

void Object::BuildCreateUpdateBlockForPlayer(UpdateData* data, Player* target) const
{
    if (!target)
        return;

    uint8 updateType = m_isNewObject ? UPDATETYPE_CREATE_OBJECT2 : UPDATETYPE_CREATE_OBJECT;
    CreateObjectBits flags = m_updateFlag;

    /** lower flag1 **/
    if (target == this)                                      // building packet for yourself
        flags.ThisIsYou = true;

    if (WorldObject const* worldObject = dynamic_cast<WorldObject const*>(this))
    {
        if (!flags.MovementUpdate && !worldObject->m_movementInfo.transport.guid.IsEmpty())
            flags.MovementTransport = true;

        if (worldObject->GetAIAnimKitId() || worldObject->GetMovementAnimKitId() || worldObject->GetMeleeAnimKitId())
            flags.AnimKit = true;
    }

    if (Unit const* unit = ToUnit())
    {
        if (unit->GetVictim())
            flags.CombatVictim = true;
    }

    ByteBuffer buf(500);
    buf << uint8(updateType);
    buf << GetPackGUID();
    buf << uint8(m_objectTypeId);

    BuildMovementUpdate(&buf, flags);
    BuildValuesUpdate(updateType, &buf, target);
    data->AddUpdateBlock(buf);
}

void Object::SendUpdateToPlayer(Player* player)
{
    // send create update to player
    UpdateData upd(player->GetMapId());
    WorldPacket packet;

    if (player->HaveAtClient(this))
        BuildValuesUpdateBlockForPlayer(&upd, player);
    else
        BuildCreateUpdateBlockForPlayer(&upd, player);
    upd.BuildPacket(&packet);
    player->SendDirectMessage(&packet);
}

void Object::SendUpdateToSet()
{
    if (Unit* unit = ToUnit())
    {
        std::list<Player*> players;
        unit->GetPlayerListInGrid(players, unit->GetVisibilityRange());
        for (auto itr = players.begin(); itr != players.end(); itr++)
        {
            UpdateData upd((*itr)->GetMapId());
            WorldPacket packet;
            if ((*itr)->HaveAtClient(this))
                BuildValuesUpdateBlockForPlayer(&upd, (*itr));
            upd.BuildPacket(&packet);
            (*itr)->GetSession()->SendPacket(&packet);
        }
    }
}

void Object::BuildValuesUpdateBlockForPlayer(UpdateData* data, Player* target) const
{
    ByteBuffer buf(500);

    buf << uint8(UPDATETYPE_VALUES);
    buf << GetPackGUID();

    BuildValuesUpdate(UPDATETYPE_VALUES, &buf, target);

    data->AddUpdateBlock(buf);
}

void Object::BuildOutOfRangeUpdateBlock(UpdateData* data) const
{
    data->AddOutOfRangeGUID(GetGUID());
}

void Object::DestroyForPlayer(Player* target, bool isDead /*= false*/) const
{
    ASSERT(target);

    WorldPackets::Misc::DestroyObject packet;
    packet.Guid = GetGUID();
    //! If the following bool is true, the client will call "void CGUnit_C::OnDeath()" for this object.
    //! OnDeath() does for eg trigger death animation and interrupts certain spells/missiles/auras/sounds...
    packet.IsDead = isDead;
    target->SendDirectMessage(packet.Write());
}

void Object::SendOutOfRangeForPlayer(Player* target) const
{
    ASSERT(target);

    UpdateData updateData(target->GetMapId());
    BuildOutOfRangeUpdateBlock(&updateData);
    WorldPacket packet;
    updateData.BuildPacket(&packet);
    target->SendDirectMessage(&packet);
}

int32 Object::GetInt32Value(uint16 index) const
{
    ASSERT(index < m_valuesCount || PrintIndexError(index, false));
    return m_int32Values[index];
}

uint32 Object::GetUInt32Value(uint16 index) const
{
    ASSERT(index < m_valuesCount || PrintIndexError(index, false));
    return m_uint32Values[index];
}

uint64 Object::GetUInt64Value(uint16 index) const
{
    ASSERT(index + 1 < m_valuesCount || PrintIndexError(index, false));
    return *((uint64*)&(m_uint32Values[index]));
}

float Object::GetFloatValue(uint16 index) const
{
    ASSERT(index < m_valuesCount || PrintIndexError(index, false));
    return m_floatValues[index];
}

uint8 Object::GetByteValue(uint16 index, uint8 offset) const
{
    ASSERT(index < m_valuesCount || PrintIndexError(index, false));
    ASSERT(offset < 4);
    return *(((uint8*)&m_uint32Values[index])+offset);
}

uint16 Object::GetUInt16Value(uint16 index, uint8 offset) const
{
    ASSERT(index < m_valuesCount || PrintIndexError(index, false));
    ASSERT(offset < 2);
    return *(((uint16*)&m_uint32Values[index])+offset);
}

ObjectGuid Object::GetGuidValue(uint16 index) const
{
    ASSERT(index + 1 < m_valuesCount || PrintIndexError(index, false));
    return *((ObjectGuid*)&(m_uint32Values[index]));
}

void Object::BuildMovementUpdate(ByteBuffer* data, CreateObjectBits flags) const
{
    Unit const* self = nullptr;
    ObjectGuid guid = GetGUID();
    uint32 movementFlags = 0;
    uint16 movementFlagsExtra = 0;

    bool hasTransportTime2 = false;
    bool hasVehicleId = false;
    bool hasFallDirection = false;
    bool hasFallData = false;
    bool hasPitch = false;
    bool hasSpline = false;
    bool hasSplineElevation = false;
    bool hasAIAnimKit = false;
    bool hasMovementAnimKit = false;
    bool hasMeleeAnimKit = false;

    std::vector<uint32> const* PauseTimes = nullptr;
    if (GameObject const* go = ToGameObject())
        PauseTimes = go->GetPauseTimes();

    // Bit content
    data->WriteBit(flags.PlayerHoverAnim);
    data->WriteBit(flags.SupressedGreetings);
    data->WriteBit(flags.Rotation);
    data->WriteBit(flags.AnimKit);
    data->WriteBit(flags.CombatVictim);
    data->WriteBit(flags.ThisIsYou);
    data->WriteBit(flags.Vehicle);
    data->WriteBit(flags.MovementUpdate);
    data->WriteBits(PauseTimes ? PauseTimes->size() : 0, 24);
    data->WriteBit(flags.NoBirthAnim);
    data->WriteBit(flags.MovementTransport);
    data->WriteBit(flags.Stationary);
    data->WriteBit(flags.AreaTrigger);
    data->WriteBit(flags.EnablePortals);
    data->WriteBit(flags.ServerTime);

    if (flags.MovementUpdate)
    {
        self = ToUnit();
        movementFlags = self->m_movementInfo.GetMovementFlags();
        movementFlagsExtra = self->m_movementInfo.GetExtraMovementFlags();
        hasSpline = self->IsSplineEnabled();

        hasTransportTime2 = self->m_movementInfo.transport.guid != 0 && self->m_movementInfo.transport.time2 != 0;
        hasVehicleId = false;
        hasPitch = self->HasUnitMovementFlag(MovementFlags(MOVEMENTFLAG_SWIMMING | MOVEMENTFLAG_FLYING)) || self->HasExtraUnitMovementFlag(MOVEMENTFLAG2_ALWAYS_ALLOW_PITCHING);
        hasFallDirection = self->HasUnitMovementFlag(MOVEMENTFLAG_FALLING);
        hasFallData = hasFallDirection || self->m_movementInfo.jump.fallTime != 0;
        hasSplineElevation = self->HasUnitMovementFlag(MOVEMENTFLAG_SPLINE_ELEVATION);

        if (GetTypeId() == TYPEID_UNIT)
            movementFlags &= MOVEMENTFLAG_MASK_CREATURE_ALLOWED;

        data->WriteBit(!movementFlags);                                         // !Has MoveFlags0
        data->WriteBit(G3D::fuzzyEq(self->GetOrientation(), 0.0f));             // Has Orientation
        data->WriteBit(guid[7]);
        data->WriteBit(guid[3]);
        data->WriteBit(guid[2]);
        if (movementFlags)
            data->WriteBits(movementFlags, 30);

        data->WriteBit(hasSpline && !self->IsPlayer());                         // !Has player spline data
        data->WriteBit(!hasPitch);                                              // !Has pitch
        data->WriteBit(hasSpline);                                              // Has spline data (independent)
        data->WriteBit(hasFallData);                                            // Has fall data
        data->WriteBit(!hasSplineElevation);                                    // !Has spline elevation
        data->WriteBit(guid[5]);
        data->WriteBit(!self->m_movementInfo.transport.guid.IsEmpty());         // Has transport data
        data->WriteBit(0);                                                      // !HasTime

        if (!self->m_movementInfo.transport.guid.IsEmpty())
        {
            ObjectGuid transGuid = self->m_movementInfo.transport.guid;

            data->WriteBit(transGuid[1]);
            data->WriteBit(hasTransportTime2);                             // Has PrevMoveTime
            data->WriteBit(transGuid[4]);
            data->WriteBit(transGuid[0]);
            data->WriteBit(transGuid[6]);
            data->WriteBit(hasVehicleId);                                  // Has VehicleRecID
            data->WriteBit(transGuid[7]);
            data->WriteBit(transGuid[5]);
            data->WriteBit(transGuid[3]);
            data->WriteBit(transGuid[2]);
        }

        data->WriteBit(guid[4]);

        if (hasSpline)
            Movement::PacketBuilder::WriteCreateBits(*self->movespline, *data);

        data->WriteBit(guid[6]);
        if (hasFallData)
            data->WriteBit(hasFallDirection);

        data->WriteBit(guid[0]);
        data->WriteBit(guid[1]);
        data->WriteBit(0);                                                      // HeightChangeFailed
        data->WriteBit(!movementFlagsExtra);                                    // !Has MoveFlags1
        if (movementFlagsExtra)
            data->WriteBits(movementFlagsExtra, 12);
    }

    if (flags.MovementTransport)
    {
        WorldObject const* self = static_cast<WorldObject const*>(this);
        ObjectGuid transGuid = self->m_movementInfo.transport.guid;
        data->WriteBit(transGuid[5]);
        data->WriteBit(hasVehicleId);                                           // Has GO transport time 3
        data->WriteBit(transGuid[0]);
        data->WriteBit(transGuid[3]);
        data->WriteBit(transGuid[6]);
        data->WriteBit(transGuid[1]);
        data->WriteBit(transGuid[4]);
        data->WriteBit(transGuid[2]);
        data->WriteBit(hasTransportTime2);                                      // Has GO transport time 2
        data->WriteBit(transGuid[7]);
    }

    if (flags.CombatVictim)
    {
        ObjectGuid victimGuid = self->GetVictim()->GetGUID();   // checked in BuildCreateUpdateBlockForPlayer
        data->WriteBit(victimGuid[2]);
        data->WriteBit(victimGuid[7]);
        data->WriteBit(victimGuid[0]);
        data->WriteBit(victimGuid[4]);
        data->WriteBit(victimGuid[5]);
        data->WriteBit(victimGuid[6]);
        data->WriteBit(victimGuid[1]);
        data->WriteBit(victimGuid[3]);
    }

    if (flags.AnimKit)
    {
        WorldObject const* self = static_cast<WorldObject const*>(this);
        hasAIAnimKit = self->GetAIAnimKitId();
        data->WriteBit(!hasAIAnimKit);
        hasMovementAnimKit = self->GetMovementAnimKitId();
        data->WriteBit(!hasMovementAnimKit);
        hasMeleeAnimKit = self->GetMeleeAnimKitId();
        data->WriteBit(!hasMeleeAnimKit);
    }

    data->FlushBits();

    if (PauseTimes && !PauseTimes->empty())
        data->append(PauseTimes->data(), PauseTimes->size());

    if (flags.MovementUpdate)
    {
        data->WriteByteSeq(guid[4]);
        *data << self->GetSpeed(MOVE_RUN_BACK);

        if (hasFallData)
        {
            if (hasFallDirection)
            {
                *data << float(self->m_movementInfo.jump.xyspeed);
                *data << float(self->m_movementInfo.jump.sinAngle);
                *data << float(self->m_movementInfo.jump.cosAngle);
            }

            *data << uint32(self->m_movementInfo.jump.fallTime);
            *data << float(self->m_movementInfo.jump.zspeed);
        }

        *data << self->GetSpeed(MOVE_SWIM_BACK);
        if (hasSplineElevation)
            *data << float(self->m_movementInfo.splineElevation);

        if (hasSpline)
            Movement::PacketBuilder::WriteCreateData(*self->movespline, *data);

        *data << float(self->GetPositionZ());
        data->WriteByteSeq(guid[5]);

        if (self->m_movementInfo.transport.guid)
        {
            ObjectGuid transGuid = self->m_movementInfo.transport.guid;

            data->WriteByteSeq(transGuid[5]);
            data->WriteByteSeq(transGuid[7]);
            *data << uint32(self->GetTransTime());
            *data << float(self->GetTransOffsetO());
            if (hasTransportTime2)
                *data << uint32(self->m_movementInfo.transport.time2);

            *data << float(self->GetTransOffsetY());
            *data << float(self->GetTransOffsetX());
            data->WriteByteSeq(transGuid[3]);
            *data << float(self->GetTransOffsetZ());
            data->WriteByteSeq(transGuid[0]);
            if (hasVehicleId)
                *data << uint32(self->m_movementInfo.transport.vehicleId);

            *data << int8(self->GetTransSeat());
            data->WriteByteSeq(transGuid[1]);
            data->WriteByteSeq(transGuid[6]);
            data->WriteByteSeq(transGuid[2]);
            data->WriteByteSeq(transGuid[4]);
        }

        *data << float(self->GetPositionX());
        *data << self->GetSpeed(MOVE_PITCH_RATE);
        data->WriteByteSeq(guid[3]);
        data->WriteByteSeq(guid[0]);
        *data << self->GetSpeed(MOVE_SWIM);
        *data << float(self->GetPositionY());
        data->WriteByteSeq(guid[7]);
        data->WriteByteSeq(guid[1]);
        data->WriteByteSeq(guid[2]);
        *data << self->GetSpeed(MOVE_WALK);

        //if (true)   // Has time, controlled by bit just after HasTransport
        *data << uint32(GameTime::GetGameTimeMS());

        *data << self->GetSpeed(MOVE_TURN_RATE);
        data->WriteByteSeq(guid[6]);
        *data << self->GetSpeed(MOVE_FLIGHT);
        if (!G3D::fuzzyEq(self->GetOrientation(), 0.0f))
            *data << float(self->GetOrientation());

        *data << self->GetSpeed(MOVE_RUN);
        if (hasPitch)
            *data << float(self->m_movementInfo.pitch);

        *data << self->GetSpeed(MOVE_FLIGHT_BACK);
    }

    if (flags.Vehicle)
    {
        *data << float(self->GetTransport() ? self->GetTransOffsetO() : self->GetOrientation());
        *data << uint32(self->GetVehicleKit()->GetVehicleInfo()->ID);
    }

    if (flags.MovementTransport)
    {
        WorldObject const* self = static_cast<WorldObject const*>(this);
        ObjectGuid transGuid = self->m_movementInfo.transport.guid;

        data->WriteByteSeq(transGuid[0]);
        data->WriteByteSeq(transGuid[5]);
        if (hasVehicleId)
            *data << uint32(self->m_movementInfo.transport.vehicleId);

        data->WriteByteSeq(transGuid[3]);
        *data << float(self->GetTransOffsetX());
        data->WriteByteSeq(transGuid[4]);
        data->WriteByteSeq(transGuid[6]);
        data->WriteByteSeq(transGuid[1]);
        *data << uint32(self->GetTransTime());
        *data << float(self->GetTransOffsetY());
        data->WriteByteSeq(transGuid[2]);
        data->WriteByteSeq(transGuid[7]);
        *data << float(self->GetTransOffsetZ());
        *data << int8(self->GetTransSeat());
        *data << float(self->GetTransOffsetO());
        if (hasTransportTime2)
            *data << uint32(self->m_movementInfo.transport.time2);
    }

    if (flags.Rotation)
        *data << uint64(ToGameObject()->GetPackedLocalRotation());

    if (flags.AreaTrigger)
    {
        // client doesn't use these values, so unk
        *data << float(0.0f);
        *data << float(0.0f);
        *data << float(0.0f);
        *data << float(0.0f);
        *data << uint8(0);
        *data << float(0.0f);
        *data << float(0.0f);
        *data << float(0.0f);
        *data << float(0.0f);
        *data << float(0.0f);
        *data << float(0.0f);
        *data << float(0.0f);
        *data << float(0.0f);
        *data << float(0.0f);
        *data << float(0.0f);
        *data << float(0.0f);
        *data << float(0.0f);
    }

    if (flags.Stationary)
    {
        WorldObject const* self = static_cast<WorldObject const*>(this);
        *data << float(self->GetStationaryO());
        *data << float(self->GetStationaryX());
        *data << float(self->GetStationaryY());
        *data << float(self->GetStationaryZ());
    }

    if (flags.CombatVictim)
    {
        ObjectGuid victimGuid = self->GetVictim()->GetGUID();   // checked in BuildCreateUpdateBlockForPlayer
        data->WriteByteSeq(victimGuid[4]);
        data->WriteByteSeq(victimGuid[0]);
        data->WriteByteSeq(victimGuid[3]);
        data->WriteByteSeq(victimGuid[5]);
        data->WriteByteSeq(victimGuid[7]);
        data->WriteByteSeq(victimGuid[6]);
        data->WriteByteSeq(victimGuid[2]);
        data->WriteByteSeq(victimGuid[1]);
    }

    if (flags.AnimKit)
    {
        WorldObject const* self = static_cast<WorldObject const*>(this);
        if (hasAIAnimKit)
            *data << uint16(self->GetAIAnimKitId());
        if (hasMovementAnimKit)
            *data << uint16(self->GetMovementAnimKitId());
        if (hasMeleeAnimKit)
            *data << uint16(self->GetMeleeAnimKitId());
    }

    if (flags.ServerTime)
        *data << uint32(GameTime::GetGameTimeMS());
}

void Object::BuildValuesUpdate(uint8 updateType, ByteBuffer* data, Player* target) const
{
    if (!target)
        return;

    ByteBuffer fieldBuffer;
    UpdateMaskPacketBuilder updateMask(m_valuesCount);

    uint32* flags = nullptr;
    uint32 visibleFlag = GetUpdateFieldData(target, flags);
    ASSERT(flags);

    for (uint16 index = 0; index < m_valuesCount; ++index)
    {
        if (_fieldNotifyFlags & flags[index] ||
            ((updateType == UPDATETYPE_VALUES ? _changesMask.GetBit(index) : m_uint32Values[index]) && (flags[index] & visibleFlag)))
        {
            updateMask.SetBit(index);
            fieldBuffer << m_uint32Values[index];
        }
    }

    updateMask.AppendToPacket(data);
    data->append(fieldBuffer);
}

void Object::AddToObjectUpdateIfNeeded()
{
    if (m_inWorld && !m_objectUpdated)
        m_objectUpdated = AddToObjectUpdate();
}

void Object::ClearUpdateMask(bool remove)
{
    _changesMask.Clear();

    if (m_objectUpdated)
    {
        if (remove)
            RemoveFromObjectUpdate();

        m_objectUpdated = false;
    }
}

void Object::BuildFieldsUpdate(Player* player, UpdateDataMapType& data_map) const
{
    UpdateDataMapType::iterator iter = data_map.find(player);

    if (iter == data_map.end())
    {
        std::pair<UpdateDataMapType::iterator, bool> p = data_map.emplace(player, UpdateData(player->GetMapId()));
        ASSERT(p.second);
        iter = p.first;
    }

    BuildValuesUpdateBlockForPlayer(&iter->second, iter->first);
}

uint32 Object::GetUpdateFieldData(Player const* target, uint32*& flags) const
{
    uint32 visibleFlag = UF_FLAG_PUBLIC;

    if (target == this)
        visibleFlag |= UF_FLAG_PRIVATE;

    switch (GetTypeId())
    {
        case TYPEID_ITEM:
        case TYPEID_CONTAINER:
            flags = ItemUpdateFieldFlags;
            if (((Item const*)this)->GetOwnerGUID() == target->GetGUID())
                visibleFlag |= UF_FLAG_OWNER | UF_FLAG_ITEM_OWNER;
            break;
        case TYPEID_UNIT:
        case TYPEID_PLAYER:
        {
            Player* plr = ToUnit()->GetCharmerOrOwnerPlayerOrPlayerItself();
            flags = UnitUpdateFieldFlags;
            if (ToUnit()->GetOwnerGUID() == target->GetGUID())
                visibleFlag |= UF_FLAG_OWNER;

            if (HasFlag(UNIT_DYNAMIC_FLAGS, UNIT_DYNFLAG_SPECIALINFO))
                if (ToUnit()->HasAuraTypeWithCaster(SPELL_AURA_EMPATHY, target->GetGUID()))
                    visibleFlag |= UF_FLAG_SPECIAL_INFO;

            if (plr && plr->IsInSameRaidWith(target))
                visibleFlag |= UF_FLAG_PARTY_MEMBER;

            if (IsCreature())
                visibleFlag |= UF_FLAG_UNIT_ALL;
            break;
        }
        case TYPEID_GAMEOBJECT:
            flags = GameObjectUpdateFieldFlags;
            if (ToGameObject()->GetOwnerGUID() == target->GetGUID())
                visibleFlag |= UF_FLAG_OWNER;
            break;
        case TYPEID_DYNAMICOBJECT:
            flags = DynamicObjectUpdateFieldFlags;
            if (ToDynObject()->GetCasterGUID() == target->GetGUID())
                visibleFlag |= UF_FLAG_OWNER;
            break;
        case TYPEID_CORPSE:
            flags = CorpseUpdateFieldFlags;
            if (ToCorpse()->GetOwnerGUID() == target->GetGUID())
                visibleFlag |= UF_FLAG_OWNER;
            break;
        case TYPEID_AREATRIGGER:
            flags = AreaTriggerUpdateFieldFlags;
            break;
        case TYPEID_OBJECT:
            break;
    }

    return visibleFlag;
}
