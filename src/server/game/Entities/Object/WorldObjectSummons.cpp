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

TempSummon* Map::SummonCreature(uint32 entry, Position const& pos, SummonCreatureExtraArgs const& summonArgs /*= { }*/)
{
    uint32 mask = UNIT_MASK_SUMMON;

    if (summonArgs.SummonProperties)
    {
        switch (summonArgs.SummonProperties->Control)
        {
            case SUMMON_CATEGORY_PET:
                mask = UNIT_MASK_GUARDIAN;
                break;
            case SUMMON_CATEGORY_PUPPET:
                mask = UNIT_MASK_PUPPET;
                break;
            case SUMMON_CATEGORY_VEHICLE:
                mask = UNIT_MASK_MINION;
                break;
            case SUMMON_CATEGORY_WILD:
            case SUMMON_CATEGORY_ALLY:
            case SUMMON_CATEGORY_UNK:
            {
                switch (SummonTitle(summonArgs.SummonProperties->Title))
                {
                    case SummonTitle::Minion:
                    case SummonTitle::Guardian:
                    case SummonTitle::Runeblade:
                        mask = UNIT_MASK_GUARDIAN;
                        break;
                    case SummonTitle::Totem:
                    case SummonTitle::Lightwell:
                        mask = UNIT_MASK_TOTEM;
                        break;
                    case SummonTitle::Vehicle:
                    case SummonTitle::Mount:
                        mask = UNIT_MASK_SUMMON;
                        break;
                    case SummonTitle::Companion:
                        mask = UNIT_MASK_MINION;
                        break;
                    default:
                        if (summonArgs.SummonProperties->Flags & 512) // Mirror Image, Summon Gargoyle
                            mask = UNIT_MASK_GUARDIAN;
                        break;
                }
                break;
            }
            default:
                return nullptr;
        }
    }

    TempSummon* summon = nullptr;
    switch (mask)
    {
        case UNIT_MASK_SUMMON:
            summon = new TempSummon(summonArgs.SummonProperties, summonArgs.Summoner, false);
            break;
        case UNIT_MASK_GUARDIAN:
            summon = new Guardian(summonArgs.SummonProperties, summonArgs.Summoner, false);
            break;
        case UNIT_MASK_PUPPET:
            summon = new Puppet(summonArgs.SummonProperties, summonArgs.Summoner);
            break;
        case UNIT_MASK_TOTEM:
            summon = new Totem(summonArgs.SummonProperties, summonArgs.Summoner);
            break;
        case UNIT_MASK_MINION:
            summon = new Minion(summonArgs.SummonProperties, summonArgs.Summoner, false);
            break;
    }

    // Create creature entity
    if (!summon->Create(GenerateLowGuid<HighGuid::Unit>(), this, entry, pos, nullptr, summonArgs.VehicleRecID, true))
    {
        delete summon;
        return nullptr;
    }

    // Inherit summoner's Phaseshift
    if (summonArgs.Summoner)
        PhasingHandler::InheritPhaseShift(summon, summonArgs.Summoner);

    TransportBase* transport = summonArgs.Summoner ? summonArgs.Summoner->GetTransport() : nullptr;
    if (transport)
    {
        float x, y, z, o;
        pos.GetPosition(x, y, z, o);
        transport->CalculatePassengerOffset(x, y, z, &o);
        summon->m_movementInfo.transport.pos.Relocate(x, y, z, o);

        // This object must be added to transport before adding to map for the client to properly display it
        transport->AddPassenger(summon);
    }

    // Initialize tempsummon fields
    summon->SetUInt32Value(UNIT_CREATED_BY_SPELL, summonArgs.SummonSpellId);
    summon->SetHomePosition(pos);
    summon->InitStats(summonArgs.SummonDuration);
    summon->SetPrivateObjectOwner(summonArgs.PrivateObjectOwner);

    // Handle health argument
    if (summonArgs.SummonHealth)
    {
        summon->SetMaxHealth(summonArgs.SummonHealth);
        summon->SetHealth(summonArgs.SummonHealth);
    }

    // Handle creature level argument
    if (summonArgs.CreatureLevel)
        summon->SetLevel(summonArgs.CreatureLevel);

    if (!AddToMap(summon->ToCreature()))
    {
        // Returning false will cause the object to be deleted - remove from transport
        if (transport)
            transport->RemovePassenger(summon);

        delete summon;
        return nullptr;
    }

    summon->InitSummon();

    // call MoveInLineOfSight for nearby creatures
    Trinity::AIRelocationNotifier notifier(*summon);
    Cell::VisitAllObjects(summon, notifier, GetVisibilityRange());

    return summon;
}

/**
* Summons group of creatures.
*
* @param group Id of group to summon.
* @param list  List to store pointers to summoned creatures.
*/

void Map::SummonCreatureGroup(uint8 group, std::list<TempSummon*>* list /*= nullptr*/)
{
    std::vector<TempSummonData> const* data = sObjectMgr->GetSummonGroup(GetId(), SUMMONER_TYPE_MAP, group);
    if (!data)
        return;

    for (std::vector<TempSummonData>::const_iterator itr = data->begin(); itr != data->end(); ++itr)
        if (TempSummon* summon = SummonCreature(itr->entry, itr->pos, SummonCreatureExtraArgs().SetSummonDuration(itr->time)))
            if (list)
                list->push_back(summon);
}

ZoneScript* WorldObject::FindZoneScript() const
{
    if (Map* map = FindMap())
    {
        if (InstanceMap* instanceMap = map->ToInstanceMap())
            return reinterpret_cast<ZoneScript*>(instanceMap->GetInstanceScript());
        else if (!map->IsBattlegroundOrArena())
        {
            if (Battlefield* bf = sBattlefieldMgr->GetBattlefieldToZoneId(map, GetZoneId()))
                return bf;
            else
                return sOutdoorPvPMgr->GetOutdoorPvPToZoneId(map, GetZoneId());
        }
    }
    return nullptr;
}

void WorldObject::SetZoneScript()
{
    m_zoneScript = FindZoneScript();
}


void WorldObject::ClearZoneScript()
{
    m_zoneScript = nullptr;
}

TempSummon* WorldObject::SummonCreature(uint32 entry, Position const& pos, TempSummonType despawnType /*= TEMPSUMMON_MANUAL_DESPAWN*/, uint32 despawnTime /*= 0*/, uint32 vehId /*= 0*/, ObjectGuid privateObjectOwner /* = ObjectGuid::Empty */)
{
    if (Map* map = FindMap())
    {
        SummonCreatureExtraArgs extraArgs;
        extraArgs.SummonDuration = despawnTime;
        extraArgs.Summoner = ToUnit();
        extraArgs.VehicleRecID = vehId;
        extraArgs.PrivateObjectOwner = privateObjectOwner;

        if (TempSummon* summon = map->SummonCreature(entry, pos, extraArgs))
        {
            summon->SetTempSummonType(despawnType);
            return summon;
        }
    }

    return nullptr;
}

TempSummon* WorldObject::SummonCreature(uint32 id, float x, float y, float z, float o /*= 0*/, TempSummonType despawnType /*= TEMPSUMMON_MANUAL_DESPAWN*/, uint32 despawnTime /*= 0*/, ObjectGuid privateObjectOwner /* = ObjectGuid::Empty */)
{
    if (!x && !y && !z)
        GetClosePoint(x, y, z, GetCombatReach());
    if (!o)
        o = GetOrientation();
    return SummonCreature(id, { x, y, z, o }, despawnType, despawnTime, 0, privateObjectOwner);
}

GameObject* WorldObject::SummonGameObject(uint32 entry, Position const& pos, QuaternionData const& rot, uint32 respawnTime, GOSummonType summonType)
{
    if (!IsInWorld())
        return nullptr;

    GameObjectTemplate const* goinfo = sObjectMgr->GetGameObjectTemplate(entry);
    if (!goinfo)
    {
        TC_LOG_ERROR("sql.sql", "Gameobject template %u not found in database!", entry);
        return nullptr;
    }

    Map* map = GetMap();
    GameObject* go = new GameObject();
    if (!go->Create(map->GenerateLowGuid<HighGuid::GameObject>(), entry, map, pos, rot, 255, GO_STATE_READY))
    {
        delete go;
        return nullptr;
    }

    PhasingHandler::InheritPhaseShift(go, this);

    go->SetRespawnTime(respawnTime);
    if (GetTypeId() == TYPEID_PLAYER || (GetTypeId() == TYPEID_UNIT && summonType == GO_SUMMON_TIMED_OR_CORPSE_DESPAWN)) //not sure how to handle this
        ToUnit()->AddGameObject(go);
    else
        go->SetSpawnedByDefault(false);

    map->AddToMap(go);
    return go;
}

GameObject* WorldObject::SummonGameObject(uint32 entry, float x, float y, float z, float ang, QuaternionData const& rot, uint32 respawnTime)
{
    if (!x && !y && !z)
    {
        GetClosePoint(x, y, z, GetCombatReach());
        ang = GetOrientation();
    }

    Position pos(x, y, z, ang);
    return SummonGameObject(entry, pos, rot, respawnTime);
}

Creature* WorldObject::SummonTrigger(float x, float y, float z, float ang, uint32 duration, CreatureAI* (*GetAI)(Creature*))
{
    TempSummonType summonType = (duration == 0) ? TEMPSUMMON_DEAD_DESPAWN : TEMPSUMMON_TIMED_DESPAWN;
    Creature* summon = SummonCreature(WORLD_TRIGGER, x, y, z, ang, summonType, duration);
    if (!summon)
        return nullptr;

    //summon->SetName(GetName());
    if (GetTypeId() == TYPEID_PLAYER || GetTypeId() == TYPEID_UNIT)
    {
        summon->SetFaction(((Unit*)this)->GetFaction());
        summon->SetLevel(((Unit*)this)->getLevel());
    }

    if (GetAI)
        summon->AIM_Initialize(GetAI(summon));
    return summon;
}

/**
* Summons group of creatures. Should be called only by instances of Creature and GameObject classes.
*
* @param group Id of group to summon.
* @param list  List to store pointers to summoned creatures.
*/
void WorldObject::SummonCreatureGroup(uint8 group, std::list<TempSummon*>* list /*= nullptr*/)
{
    ASSERT((GetTypeId() == TYPEID_GAMEOBJECT || GetTypeId() == TYPEID_UNIT) && "Only GOs and creatures can summon npc groups!");

    std::vector<TempSummonData> const* data = sObjectMgr->GetSummonGroup(GetEntry(), GetTypeId() == TYPEID_GAMEOBJECT ? SUMMONER_TYPE_GAMEOBJECT : SUMMONER_TYPE_CREATURE, group);
    if (!data)
    {
        TC_LOG_WARN("scripts", "%s (%s) tried to summon non-existing summon group %u.", GetName().c_str(), GetGUID().ToString().c_str(), group);
        return;
    }

    for (std::vector<TempSummonData>::const_iterator itr = data->begin(); itr != data->end(); ++itr)
        if (TempSummon* summon = SummonCreature(itr->entry, itr->pos, itr->type, itr->time))
            if (list)
                list->push_back(summon);
}

Creature* WorldObject::FindNearestCreature(uint32 entry, float range, bool alive) const
{
    Creature* creature = nullptr;
    Trinity::NearestCreatureEntryWithLiveStateInObjectRangeCheck checker(*this, entry, alive, range);
    Trinity::CreatureLastSearcher<Trinity::NearestCreatureEntryWithLiveStateInObjectRangeCheck> searcher(this, creature, checker);
    Cell::VisitAllObjects(this, searcher, range);
    return creature;
}

GameObject* WorldObject::FindNearestGameObject(uint32 entry, float range) const
{
    GameObject* go = nullptr;
    Trinity::NearestGameObjectEntryInObjectRangeCheck checker(*this, entry, range);
    Trinity::GameObjectLastSearcher<Trinity::NearestGameObjectEntryInObjectRangeCheck> searcher(this, go, checker);
    Cell::VisitGridObjects(this, searcher, range);
    return go;
}

GameObject* WorldObject::FindNearestGameObjectOfType(GameobjectTypes type, float range) const
{
    GameObject* go = nullptr;
    Trinity::NearestGameObjectTypeInObjectRangeCheck checker(*this, type, range);
    Trinity::GameObjectLastSearcher<Trinity::NearestGameObjectTypeInObjectRangeCheck> searcher(this, go, checker);
    Cell::VisitGridObjects(this, searcher, range);
    return go;
}

Player* WorldObject::SelectNearestPlayer(float distance) const
{
    Player* target = nullptr;

    Trinity::NearestPlayerInObjectRangeCheck checker(this, distance);
    Trinity::PlayerLastSearcher<Trinity::NearestPlayerInObjectRangeCheck> searcher(this, target, checker);
    Cell::VisitWorldObjects(this, searcher, distance);

    return target;
}

ObjectGuid WorldObject::GetCharmerOrOwnerOrOwnGUID() const
{
    ObjectGuid guid = GetCharmerOrOwnerGUID();
    if (!guid.IsEmpty())
        return guid;
    return GetGUID();
}

Unit* WorldObject::GetOwner() const
{
    return ObjectAccessor::GetUnit(*this, GetOwnerGUID());
}

Unit* WorldObject::GetCharmerOrOwner() const
{
    if (Unit const* unit = ToUnit())
        return unit->GetCharmerOrOwner();
    else if (GameObject const* go = ToGameObject())
        return go->GetOwner();

    return nullptr;
}

Unit* WorldObject::GetCharmerOrOwnerOrSelf() const
{
    if (Unit* u = GetCharmerOrOwner())
        return u;

    return const_cast<WorldObject*>(this)->ToUnit();
}

Unit* WorldObject::GetCharmerOrOwnerOrCreatorOrSelf() const
{
    Unit* u = GetCharmerOrOwner();
    if (!u)
        u = const_cast<WorldObject*>(this)->ToUnit();

    if (u)
        if (Unit* creator = ObjectAccessor::GetUnit(*this, u->GetCreatorGUID()))
            u = creator;

    return u;
}

Player* WorldObject::GetCharmerOrOwnerPlayerOrPlayerItself() const
{
    ObjectGuid guid = GetCharmerOrOwnerGUID();
    if (guid.IsPlayer())
        return ObjectAccessor::GetPlayer(*this, guid);

    return const_cast<WorldObject*>(this)->ToPlayer();
}

Player* WorldObject::GetAffectingPlayer() const
{
    if (!GetCharmerOrOwnerGUID())
        return const_cast<WorldObject*>(this)->ToPlayer();

    if (Unit* owner = GetCharmerOrOwner())
        return owner->GetCharmerOrOwnerPlayerOrPlayerItself();

    return nullptr;
}

Player* WorldObject::GetSpellModOwner() const
{
    if (Player* player = const_cast<WorldObject*>(this)->ToPlayer())
        return player;

    if (GetTypeId() == TYPEID_UNIT)
    {
        Creature const* creature = ToCreature();
        if (creature->HasUnitTypeMask(UNIT_MASK_PET | UNIT_MASK_TOTEM | UNIT_MASK_GUARDIAN | UNIT_MASK_HUNTER_PET | UNIT_MASK_MINION))
        {
            if (Unit* owner = creature->GetOwner())
            {
                // The Fire Elemental's native owner is its summoning totem.
                // Resolve only that exact guardian/totem chain; other summons
                // retain the ordinary immediate-player ownership contract.
                if (creature->IsGuardian() && creature->GetEntry() == 15438)
                    if (Totem* totem = owner->ToTotem(); totem && totem->GetEntry() == 15439)
                        if (Unit* totemOwner = totem->GetOwner())
                            return totemOwner->ToPlayer();
                return owner->ToPlayer();
            }
        }
    }
    else if (GetTypeId() == TYPEID_GAMEOBJECT)
    {
        GameObject const* go = ToGameObject();
        if (Unit* owner = go->GetOwner())
            return owner->ToPlayer();
    }

    return nullptr;
}
