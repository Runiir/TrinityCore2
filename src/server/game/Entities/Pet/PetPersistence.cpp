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


#include "CharmInfo.h"
#include "Common.h"
#include "DatabaseEnv.h"
#include "Log.h"
#include "WorldPacket.h"
#include "ObjectMgr.h"
#include "PhasingHandler.h"
#include "SpellMgr.h"
#include "Pet.h"
#include "Formulas.h"
#include "SpellHistory.h"
#include "SpellAuras.h"
#include "SpellAuraEffects.h"
#include "Unit.h"
#include "Util.h"
#include "Group.h"
#include "Opcodes.h"
#include "WorldSession.h"
#include "Player.h"
#include "GameTime.h"
#include "SpellInfo.h"
#include <memory>
#include "Map.h"
#include "CreatureAI.h"
#include <sstream>

bool Pet::LoadPetData(Player* owner, uint32 petEntry, uint32 petnumber, bool current)
{
    m_loading = true;

    PlayerPetData* playerPetData;

    if (petnumber)
    {
        playerPetData = owner->GetPlayerPetDataById(petnumber);
    }
    else if ((getPetType() == SUMMON_PET) && petEntry)
    {
        playerPetData = owner->GetPlayerPetDataByCreatureId(petEntry);
    }
    else if (getPetType() == HUNTER_PET)
    {
        playerPetData = owner->GetPlayerPetDataBySlot(petEntry);
    }
    else
    {
        playerPetData = owner->GetPlayerPetDataCurrent();
    }

    if (!playerPetData)
    {
        m_loading = false;
        return false;
    }

    petEntry = playerPetData->CreatureId;
    if (!petEntry)
        return false;

    uint32 summonSpellId = playerPetData->SummonSpellId;
    SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(summonSpellId);

    bool isTemporarySummon = spellInfo && spellInfo->GetDuration() > 0;
    if (current && isTemporarySummon)
        return false;

    PetType petType = playerPetData->Type;
    if (petType == HUNTER_PET)
    {
        CreatureTemplate const* creatureInfo = sObjectMgr->GetCreatureTemplate(petEntry);
        if (!creatureInfo)
        {
            owner->GetSession()->SendStableResult(STABLE_ERR_STABLE);
            return false;
        }

        if (!creatureInfo->IsTameable(owner->CanTameExoticPets()))
        {
            owner->GetSession()->SendStableResult(STABLE_ERR_EXOTIC);
            return false;
        }
    }

    uint32 petId = playerPetData->PetId;

    if (current && owner->IsPetNeedBeTemporaryUnsummoned())
    {
        owner->SetTemporaryUnsummonedPetNumber(petId);
        return false;
    }

    Map* map = owner->GetMap();
    ObjectGuid::LowType guid = map->GenerateLowGuid<HighGuid::Pet>();
    if (!Create(guid, map, petEntry, petId))
        return false;

    PhasingHandler::InheritPhaseShift(this, owner);

    setPetType(petType);
    SetFaction(owner->GetFaction());
    SetUInt32Value(UNIT_CREATED_BY_SPELL, summonSpellId);

    if (IsCritter())
    {
        Position pos = owner->GetPosition();
        owner->MovePositionToFirstCollision(pos, DEFAULT_FOLLOW_DISTANCE_PET, DEFAULT_FOLLOW_ANGLE);
        Relocate(pos.GetPositionX(), pos.GetPositionY(), pos.GetPositionZ(), owner->GetOrientation());

        if (!IsPositionValid())
        {
            TC_LOG_ERROR("entities.pet", "Pet (guidlow %d, entry %d) not loaded. Suggested coordinates isn't valid (X: %f Y: %f)",
                GetGUID().GetCounter(), GetEntry(), GetPositionX(), GetPositionY());
            return false;
        }

        map->AddToMap(this->ToCreature());
        return true;
    }

    m_charmInfo->SetPetNumber(petId, IsPermanentPetFor(owner));

    SetDisplayId(playerPetData->DisplayId, true);
    uint32 petlevel = playerPetData->Petlevel;
    SetUInt32Value(UNIT_NPC_FLAGS, UNIT_NPC_FLAG_NONE);
    SetName(playerPetData->Name);

    switch (getPetType())
    {
        case SUMMON_PET:
            petlevel = owner->getLevel();
            SetByteValue(UNIT_FIELD_BYTES_0, UNIT_BYTES_0_OFFSET_CLASS, uint8(CLASS_MAGE));
            SetUInt32Value(UNIT_FIELD_FLAGS, UNIT_FLAG_PLAYER_CONTROLLED);
            break;
        case HUNTER_PET:
            SetByteValue(UNIT_FIELD_BYTES_0, UNIT_BYTES_0_OFFSET_CLASS, CLASS_WARRIOR);
            SetByteValue(UNIT_FIELD_BYTES_0, UNIT_BYTES_0_OFFSET_GENDER, GENDER_NONE);
            SetSheath(SHEATH_STATE_MELEE);
            SetByteFlag(UNIT_FIELD_BYTES_2, UNIT_BYTES_2_OFFSET_PET_FLAGS, playerPetData->Renamed ? UNIT_CAN_BE_ABANDONED : UNIT_CAN_BE_RENAMED | UNIT_CAN_BE_ABANDONED);
            SetUInt32Value(UNIT_FIELD_FLAGS, UNIT_FLAG_PLAYER_CONTROLLED);
            break;
        default:
            if (!IsPetGhoul())
                TC_LOG_ERROR("entities.pet", "Pet have incorrect type (%u) for pet loading.", getPetType());
            break;
    }

    SetUInt32Value(UNIT_FIELD_PET_NAME_TIMESTAMP, uint32(GameTime::GetGameTime())); // cast can't be helped here
    SetCreatorGUID(owner->GetGUID());

    InitStatsForLevel(petlevel);
    SetUInt32Value(UNIT_FIELD_PETEXPERIENCE, playerPetData->PetExp);

    SynchronizeLevelWithOwner();

    Position pos = owner->GetPosition();
    owner->MovePositionToFirstCollision(pos, DEFAULT_FOLLOW_DISTANCE_PET, float(M_PI_2));
    Relocate(pos.GetPositionX(), pos.GetPositionY(), pos.GetPositionZ(), owner->GetOrientation());

    if (!IsPositionValid())
    {
        TC_LOG_ERROR("entities.pet", "Pet (guidlow %d, entry %d) not loaded. Suggested coordinates isn't valid (X: %f Y: %f)",
            GetGUID().GetCounter(), GetEntry(), GetPositionX(), GetPositionY());
        return false;
    }

    SetReactState(ReactStates(playerPetData->Reactstate));
    SetCanModifyStats(true);

    if (getPetType() == SUMMON_PET && !current)              //all (?) summon pets come with full health when called, but not when they are current
        SetPower(POWER_MANA, GetMaxPower(POWER_MANA));
    else
    {
        uint32 savedhealth = playerPetData->SavedHealth;
        uint32 savedmana = playerPetData->SavedMana;
        if (!savedhealth && getPetType() == HUNTER_PET)
            setDeathState(JUST_DIED);
        else
        {
            SetHealth(savedhealth > GetMaxHealth() ? GetMaxHealth() : savedhealth);
            SetPower(POWER_MANA, savedmana > uint32(GetMaxPower(POWER_MANA)) ? GetMaxPower(POWER_MANA) : savedmana);
        }
    }

    SetSlot(playerPetData->Slot);

    // Send fake summon spell cast - this is needed for correct cooldown application for spells
    // Example: 46584 - without this cooldown (which should be set always when pet is loaded) isn't set clientside
    /// @todo pets should be summoned from real cast instead of just faking it?
    if (summonSpellId)
    {
        WorldPacket data(SMSG_SPELL_GO, (8+8+4+4+2));
        data << owner->GetPackGUID();
        data << owner->GetPackGUID();
        data << uint8(0);
        data << uint32(summonSpellId);
        data << uint32(256); // CAST_FLAG_UNKNOWN3
        data << uint32(0);
        data << uint32(getMSTime());
        owner->SendMessageToSet(&data, true);
    }

    owner->SetMinion(this, true);
    map->AddToMap(ToCreature());

    InitTalentForLevel();                                   // set original talents points before spell loading

    uint32 timediff = uint32(GameTime::GetGameTime() - playerPetData->Timediff);
    _LoadAuras(timediff);

    // load action bar, if data broken will fill later by default spells.
    if (!isTemporarySummon)
    {
        m_charmInfo->LoadPetActionBar(playerPetData->Actionbar);

        _LoadSpells();
        InitTalentForLevel();                               // re-init to check talent count
        _LoadSpellCooldowns();
        LearnPetPassives();
        InitLevelupSpellsForLevel();
        if (map->IsBattleArena())
            RemoveArenaAuras();

        CastPetAuras(current);
        CastPetScalingAuras();
    }

    CleanupActionBar();                                     // remove unknown spells from action bar after load
    UpdateAllStats();
    SetFullHealth();                                        // Set full health and mana after pet scaling auras has been applied

    if (IsHunterPet())
        CastSpell(this, SPELL_PET_ENERGIZE, true);
    else
        SetPower(POWER_MANA, GetMaxPower(POWER_MANA));

    if (IsPetGhoul())
    {
        CastSpell(this, SPELL_PET_RISEN_GHOUL_SPAWN_IN, true);
        CastSpell(this, SPELL_PET_RISEN_GHOUL_SELF_STUN, true);
    }

    TC_LOG_DEBUG("entities.pet", "New Pet has guid %u", GetGUID().GetCounter());

    owner->PetSpellInitialize();

    if (owner->GetGroup())
        owner->SetGroupUpdateFlag(GROUP_UPDATE_PET);

    owner->SendTalentsInfoData(true);

    if (getPetType() == HUNTER_PET)
    {
        CharacterDatabasePreparedStatement* stmt = CharacterDatabase.GetPreparedStatement(CHAR_SEL_PET_DECLINED_NAME);
        stmt->setUInt32(0, owner->GetGUID().GetCounter());
        stmt->setUInt32(1, GetCharmInfo()->GetPetNumber());
        PreparedQueryResult result = CharacterDatabase.Query(stmt);

        if (result)
        {
            delete m_declinedname;
            m_declinedname = new DeclinedName;
            Field* fields2 = result->Fetch();
            for (uint8 i = 0; i < MAX_DECLINED_NAME_CASES; ++i)
            {
                m_declinedname->name[i] = fields2[i].GetString();
            }
        }
    }

    //set last used pet number (for use in BG's)
    if (owner->GetTypeId() == TYPEID_PLAYER && isControlled() && !isTemporarySummoned() && (getPetType() == SUMMON_PET || getPetType() == HUNTER_PET))
        owner->ToPlayer()->SetLastPetNumber(petId);

    // must be after SetMinion (owner guid check)
    LoadTemplateImmunities();
    m_loading = false;

    return true;
}

void Pet::SavePetToDB(PetSaveMode mode)
{
    if (!GetEntry())
        return;

    // save only fully controlled creature
    if (!isControlled())
        return;

    // not save not player pets
    if (!GetOwnerOrCreatorGUID().IsPlayer())
        return;

    uint32 curhealth = GetHealth();
    uint32 curmana = GetPower(POWER_MANA);

    CharacterDatabaseTransaction trans = CharacterDatabase.BeginTransaction();
    // save auras before possibly removing them
    _SaveAuras(trans);

    _SaveSpells(trans);
    GetSpellHistory()->SaveToDB<Pet>(trans);
    CharacterDatabase.CommitTransaction(trans);

    PlayerPetData* playerPetData = GetOwner()->GetPlayerPetDataById(m_charmInfo->GetPetNumber());
    std::unique_ptr<PlayerPetData> newPlayerPetData; // used when creating a new pet

    // save as new if no data for Pet in PlayerPetDataStore
    if (mode < PET_SAVE_NEW_PET && !playerPetData)
        mode = PET_SAVE_NEW_PET;

    if (mode == PET_SAVE_NEW_PET)
    {
        Optional<uint8> slot = IsHunterPet() ? GetOwner()->GetFirstUnusedActivePetSlot() : GetOwner()->GetFirstUnusedPetSlot();

        if (slot)
        {
            SetSlot(*slot);
            newPlayerPetData = std::make_unique<PlayerPetData>();
            playerPetData = newPlayerPetData.get();
        }
        else
            mode = PET_SAVE_AS_DELETED;
    }

    if (mode == PET_SAVE_DISMISS || mode == PET_SAVE_LOGOUT)
        RemoveAllAuras();

    // whole pet is saved to DB
    if (mode >= PET_SAVE_CURRENT_STATE)
    {
        ObjectGuid::LowType ownerLowGUID = GetOwnerOrCreatorGUID().GetCounter();
        std::string name = m_name;
        CharacterDatabase.EscapeString(name);
        trans = CharacterDatabase.BeginTransaction();
        // remove current data

        CharacterDatabasePreparedStatement* stmt = CharacterDatabase.GetPreparedStatement(CHAR_DEL_CHAR_PET_BY_ID);
        stmt->setUInt32(0, m_charmInfo->GetPetNumber());
        trans->Append(stmt);

        uint32 petId = m_charmInfo->GetPetNumber();

        // save pet
        stmt = CharacterDatabase.GetPreparedStatement(CHAR_INS_PET);
        stmt->setUInt32(0, petId);
        stmt->setUInt32(1, GetEntry());
        stmt->setUInt64(2, ownerLowGUID);
        stmt->setUInt32(3, GetNativeDisplayId());
        stmt->setUInt8(4, getLevel());
        stmt->setUInt32(5, GetUInt32Value(UNIT_FIELD_PETEXPERIENCE));
        stmt->setUInt8(6, GetReactState());
        stmt->setInt16(7, m_petSlot);
        stmt->setString(8, m_name);
        stmt->setUInt8(9, HasByteFlag(UNIT_FIELD_BYTES_2, UNIT_BYTES_2_OFFSET_PET_FLAGS, UNIT_CAN_BE_RENAMED) ? 0 : 1);
        stmt->setUInt8(10, mode == PET_SAVE_DISMISS ? 0 : 1);
        stmt->setUInt32(11, curhealth);
        stmt->setUInt32(12, curmana);

        stmt->setString(13, GenerateActionBarData());

        stmt->setUInt32(14, GameTime::GetGameTime()); // unsure about this
        stmt->setUInt32(15, GetUInt32Value(UNIT_CREATED_BY_SPELL));
        stmt->setUInt8(16, getPetType());
        trans->Append(stmt);

        CharacterDatabase.CommitTransaction(trans);

        if (m_petSlot > PET_SLOT_LAST)
            TC_LOG_ERROR("sql.sql", "Pet::SavePetToDB: bad slot %u for pet %u!", m_petSlot, petId);

        playerPetData->PetId = petId;
        playerPetData->CreatureId = GetEntry();
        playerPetData->Owner = ownerLowGUID;
        playerPetData->DisplayId = GetNativeDisplayId();
        playerPetData->Petlevel = getLevel();
        playerPetData->PetExp = GetUInt32Value(UNIT_FIELD_PETEXPERIENCE);
        playerPetData->Reactstate = GetReactState();
        playerPetData->Slot = m_petSlot;
        playerPetData->Name = m_name;
        playerPetData->Renamed = HasByteFlag(UNIT_FIELD_BYTES_2, UNIT_BYTES_2_OFFSET_PET_FLAGS, UNIT_CAN_BE_RENAMED) ? 0 : 1;
        playerPetData->Active = mode == PET_SAVE_DISMISS ? 0 : 1;
        playerPetData->SavedHealth = curhealth;
        playerPetData->SavedMana = curmana;
        playerPetData->Actionbar = GenerateActionBarData();
        playerPetData->Timediff = GameTime::GetGameTime();
        playerPetData->SummonSpellId = GetUInt32Value(UNIT_CREATED_BY_SPELL);
        playerPetData->Type = getPetType();

        if (mode == PET_SAVE_NEW_PET && newPlayerPetData)
            GetOwner()->AddToPlayerPetDataStore(std::move(newPlayerPetData));
    }
    // delete
    else
    {
        RemoveAllAuras();
        DeleteFromDB(m_charmInfo->GetPetNumber());

        GetOwner()->DeleteFromPlayerPetDataStore(m_charmInfo->GetPetNumber());
        GetOwner()->GetSession()->SendStablePet(ObjectGuid::Empty);
    }
}

void Pet::DeleteFromDB(ObjectGuid::LowType guidlow)
{
    CharacterDatabaseTransaction trans = CharacterDatabase.BeginTransaction();

    CharacterDatabasePreparedStatement* stmt = CharacterDatabase.GetPreparedStatement(CHAR_DEL_CHAR_PET_BY_ID);
    stmt->setUInt32(0, guidlow);
    trans->Append(stmt);

    stmt = CharacterDatabase.GetPreparedStatement(CHAR_DEL_CHAR_PET_DECLINEDNAME);
    stmt->setUInt32(0, guidlow);
    trans->Append(stmt);

    stmt = CharacterDatabase.GetPreparedStatement(CHAR_DEL_PET_AURAS);
    stmt->setUInt32(0, guidlow);
    trans->Append(stmt);

    stmt = CharacterDatabase.GetPreparedStatement(CHAR_DEL_PET_SPELLS);
    stmt->setUInt32(0, guidlow);
    trans->Append(stmt);

    stmt = CharacterDatabase.GetPreparedStatement(CHAR_DEL_PET_SPELL_COOLDOWNS);
    stmt->setUInt32(0, guidlow);
    trans->Append(stmt);

    CharacterDatabase.CommitTransaction(trans);
}

void Pet::_LoadSpellCooldowns()
{
    CharacterDatabasePreparedStatement* stmt = CharacterDatabase.GetPreparedStatement(CHAR_SEL_PET_SPELL_COOLDOWN);
    stmt->setUInt32(0, m_charmInfo->GetPetNumber());
    PreparedQueryResult cooldownsResult = CharacterDatabase.Query(stmt);

    GetSpellHistory()->LoadFromDB<Pet>(cooldownsResult);
}

void Pet::_LoadSpells()
{
    CharacterDatabasePreparedStatement* stmt = CharacterDatabase.GetPreparedStatement(CHAR_SEL_PET_SPELL);
    stmt->setUInt32(0, m_charmInfo->GetPetNumber());
    PreparedQueryResult result = CharacterDatabase.Query(stmt);

    if (result)
    {
        do
        {
            Field* fields = result->Fetch();

            addSpell(fields[0].GetUInt32(), ActiveStates(fields[1].GetUInt8()), PETSPELL_UNCHANGED);
        }
        while (result->NextRow());
    }
}

void Pet::_SaveSpells(CharacterDatabaseTransaction& trans)
{
    CharacterDatabasePreparedStatement* stmt = CharacterDatabase.GetPreparedStatement(CHAR_DEL_PET_SPELLS);
    stmt->setUInt32(0, m_charmInfo->GetPetNumber());
    trans->Append(stmt);

    for (PetSpellMap::iterator itr = m_spells.begin(), next = m_spells.begin(); itr != m_spells.end(); itr = next)
    {
        ++next;

        // prevent saving family passives to DB
        if (itr->second.type == PETSPELL_FAMILY)
            continue;

        switch (itr->second.state)
        {
            case PETSPELL_REMOVED:
                m_spells.erase(itr);
                continue;
            case PETSPELL_CHANGED:
            case PETSPELL_NEW:
            case PETSPELL_UNCHANGED:
                stmt = CharacterDatabase.GetPreparedStatement(CHAR_INS_PET_SPELL);
                stmt->setUInt32(0, m_charmInfo->GetPetNumber());
                stmt->setUInt32(1, itr->first);
                stmt->setUInt8(2, itr->second.active);
                trans->Append(stmt);
                break;
        }
        itr->second.state = PETSPELL_UNCHANGED;
    }
}

void Pet::_LoadAuras(uint32 timediff)
{
    TC_LOG_DEBUG("entities.pet", "Loading auras for pet %u", GetGUID().GetCounter());

    CharacterDatabasePreparedStatement* stmt = CharacterDatabase.GetPreparedStatement(CHAR_SEL_PET_AURA);
    stmt->setUInt32(0, m_charmInfo->GetPetNumber());
    PreparedQueryResult result = CharacterDatabase.Query(stmt);

    if (result)
    {
        do
        {
            int32 damage[3];
            int32 baseDamage[3];
            Field* fields = result->Fetch();
            ObjectGuid caster_guid(fields[0].GetUInt64());
            // nullptr guid stored - pet is the caster of the spell - see Pet::_SaveAuras
            if (!caster_guid)
                caster_guid = GetGUID();
            uint32 spellid = fields[1].GetUInt32();
            uint8 effmask = fields[2].GetUInt8();
            uint8 recalculatemask = fields[3].GetUInt8();
            uint8 stackcount = fields[4].GetUInt8();
            damage[0] = fields[5].GetInt32();
            damage[1] = fields[6].GetInt32();
            damage[2] = fields[7].GetInt32();
            baseDamage[0] = fields[8].GetInt32();
            baseDamage[1] = fields[9].GetInt32();
            baseDamage[2] = fields[10].GetInt32();
            int32 maxduration = fields[11].GetInt32();
            int32 remaintime = fields[12].GetInt32();
            uint8 remaincharges = fields[13].GetUInt8();
            float critChance = fields[14].GetFloat();
            bool applyResilience = fields[15].GetBool();

            SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spellid);
            if (!spellInfo)
            {
                TC_LOG_ERROR("entities.pet", "Unknown aura (spellid %u), ignore.", spellid);
                continue;
            }

            // negative effects should continue counting down after logout
            if (remaintime != -1 && (!spellInfo->IsPositive() || spellInfo->HasAttribute(SPELL_ATTR4_AURA_EXPIRES_OFFLINE)))
            {
                if (remaintime/IN_MILLISECONDS <= int32(timediff))
                    continue;

                remaintime -= timediff*IN_MILLISECONDS;
            }

            // prevent wrong values of remaincharges
            if (spellInfo->ProcCharges)
            {
                if (remaincharges <= 0 || remaincharges > spellInfo->ProcCharges)
                    remaincharges = spellInfo->ProcCharges;
            }
            else
                remaincharges = 0;

            AuraCreateInfo createInfo(spellInfo, effmask, this);
            createInfo
                .SetCasterGUID(caster_guid)
                .SetBaseAmount(baseDamage);

            if (Aura* aura = Aura::TryCreate(createInfo))
            {
                if (!aura->CanBeSaved())
                {
                    aura->Remove();
                    continue;
                }
                aura->SetLoadedState(maxduration, remaintime, remaincharges, stackcount, recalculatemask, critChance, applyResilience, &damage[0]);
                aura->ApplyForTargets();
                TC_LOG_DEBUG("entities.pet", "Added aura spellid %u, effectmask %u", spellInfo->Id, effmask);
            }
        }
        while (result->NextRow());
    }
}

void Pet::_SaveAuras(CharacterDatabaseTransaction& trans)
{
    CharacterDatabasePreparedStatement* stmt = CharacterDatabase.GetPreparedStatement(CHAR_DEL_PET_AURAS);
    stmt->setUInt32(0, m_charmInfo->GetPetNumber());
    trans->Append(stmt);

    for (AuraMap::const_iterator itr = m_ownedAuras.begin(); itr != m_ownedAuras.end(); ++itr)
    {
        // check if the aura has to be saved
        if (!itr->second->CanBeSaved() || IsPetAura(itr->second))
            continue;

        Aura* aura = itr->second;

        int32 damage[MAX_SPELL_EFFECTS];
        int32 baseDamage[MAX_SPELL_EFFECTS];
        uint8 effMask = 0;
        uint8 recalculateMask = 0;
        for (uint8 i = 0; i < MAX_SPELL_EFFECTS; ++i)
        {
            if (aura->GetEffect(i))
            {
                baseDamage[i] = aura->GetEffect(i)->GetBaseAmount();
                damage[i] = aura->GetEffect(i)->GetAmount();
                effMask |= (1<<i);
                if (aura->GetEffect(i)->CanBeRecalculated())
                    recalculateMask |= (1<<i);
            }
            else
            {
                baseDamage[i] = 0;
                damage[i] = 0;
            }
        }

        // don't save guid of caster in case we are caster of the spell - guid for pet is generated every pet load, so it won't match saved guid anyways
        ObjectGuid casterGUID = (itr->second->GetCasterGUID() == GetGUID()) ? ObjectGuid::Empty : itr->second->GetCasterGUID();

        uint8 index = 0;

        stmt = CharacterDatabase.GetPreparedStatement(CHAR_INS_PET_AURA);
        stmt->setUInt32(index++, m_charmInfo->GetPetNumber());
        stmt->setUInt64(index++, casterGUID.GetRawValue());
        stmt->setUInt32(index++, itr->second->GetId());
        stmt->setUInt8(index++, effMask);
        stmt->setUInt8(index++, recalculateMask);
        stmt->setUInt8(index++, itr->second->GetStackAmount());
        stmt->setInt32(index++, damage[0]);
        stmt->setInt32(index++, damage[1]);
        stmt->setInt32(index++, damage[2]);
        stmt->setInt32(index++, baseDamage[0]);
        stmt->setInt32(index++, baseDamage[1]);
        stmt->setInt32(index++, baseDamage[2]);
        stmt->setInt32(index++, itr->second->GetMaxDuration());
        stmt->setInt32(index++, itr->second->GetDuration());
        stmt->setUInt8(index++, itr->second->GetCharges());
        stmt->setFloat(index++, itr->second->GetCritChance());
        stmt->setBool(index++, itr->second->CanApplyResilience());

        trans->Append(stmt);
    }
}

void Pet::resetTalentsForAllPetsOf(Player* /*owner*/, Pet* /*onlinePet*/ /*= nullptr*/)
{
    /*
    // not need after this call
    if (owner->HasAtLoginFlag(AT_LOGIN_RESET_PET_TALENTS))
        owner->RemoveAtLoginFlag(AT_LOGIN_RESET_PET_TALENTS, true);

    // reset for online
    if (onlinePet)
        onlinePet->resetTalents();

    // now need only reset for offline pets (all pets except online case)
    uint32 exceptPetNumber = onlinePet ? onlinePet->GetCharmInfo()->GetPetNumber() : 0;

    PreparedStatement* stmt = CharacterDatabase.GetPreparedStatement(CHAR_SEL_CHAR_PET);
    stmt->setUInt32(0, owner->GetGUID().GetCounter());
    stmt->setUInt32(1, exceptPetNumber);
    PreparedQueryResult resultPets = CharacterDatabase.Query(stmt);

    // no offline pets
    if (!resultPets)
        return;

    stmt = CharacterDatabase.GetPreparedStatement(CHAR_SEL_PET_SPELL_LIST);
    stmt->setUInt32(0, owner->GetGUID().GetCounter());
    stmt->setUInt32(1, exceptPetNumber);
    PreparedQueryResult result = CharacterDatabase.Query(stmt);

    if (!result)
        return;

    bool need_comma = false;
    std::ostringstream ss;
    ss << "DELETE FROM pet_spell WHERE guid IN (";

    do
    {
        Field* fields = resultPets->Fetch();

        uint32 id = fields[0].GetUInt32();

        if (need_comma)
            ss << ',';

        ss << id;

        need_comma = true;
    } while (resultPets->NextRow());

    ss << ") AND spell IN (";

    bool need_execute = false;
    do
    {
        Field* fields = result->Fetch();

        uint32 spell = fields[0].GetUInt32();

        if (!GetTalentSpellCost(spell))
            continue;

        if (need_execute)
            ss << ',';

        ss << spell;

        need_execute = true;
    }
    while (result->NextRow());

    if (!need_execute)
        return;

    ss << ')';

    CharacterDatabase.Execute(ss.str().c_str());
    */
}

std::string Pet::GenerateActionBarData() const
{
    std::ostringstream ss;

    for (uint32 i = ACTION_BAR_INDEX_START; i < ACTION_BAR_INDEX_END; ++i)
    {
        ss << uint32(m_charmInfo->GetActionBarEntry(i)->GetType()) << ' '
            << uint32(m_charmInfo->GetActionBarEntry(i)->GetAction()) << ' ';
    }

    return ss.str();
}
