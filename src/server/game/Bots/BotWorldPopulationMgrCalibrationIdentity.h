#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_CALIBRATION_IDENTITY_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_CALIBRATION_IDENTITY_H

#include <cmath>

#include "Define.h"
#include "PetDefines.h"
#include "ObjectGuid.h"

#include <string>
#include <utility>
#include <vector>

class Player;

namespace BotWorldPopulationMgrCalibrationIdentity
{
enum class HunterPetObservationStatus : uint8
{
    NotHunter = 0,
    LifecycleUnavailable,
    IdentityInvalid,
    IdentityObserved
};

struct HunterPetIdentitySnapshot
{
    uint32 PetId = 0;
    uint32 PetEntry = 0;
    ObjectGuid PetOwnerGuid;
    std::vector<std::pair<uint32, uint8>> Spellbook;
    std::string SpellbookSha256;
    std::vector<uint32> AutocastSpellIds;
};

struct OrdinaryPetSpellIdentity
{
    uint32 SpellId = 0;
    uint8 Active = 0;
    uint8 Type = 0;
};

struct OrdinaryPetSetupSnapshot
{
    bool Present = false;
    bool InWorld = false;
    bool Alive = false;
    bool Owned = false;
    bool Permanent = false;
    ObjectGuid Guid;
    uint32 Entry = 0;
    uint32 FamilyId = 0;
    uint32 PetType = uint32(MAX_PET_TYPE);
    uint32 CreatedBySpellId = 0;
    uint32 Health = 0;
    uint32 MaxHealth = 0;
    uint32 PowerType = 0;
    uint32 Power = 0;
    uint32 MaxPower = 0;
    std::vector<OrdinaryPetSpellIdentity> Spellbook;
    std::string SpellbookSha256;
    std::vector<uint32> AutocastSpellIds;
};

OrdinaryPetSetupSnapshot ObserveOrdinaryPetSetup(Player const* bot);
bool OrdinaryPersistentPetMatches(OrdinaryPetSetupSnapshot const& snapshot,
    uint32 expectedEntry, uint32 expectedFamilyId, uint32 expectedPetType,
    uint32 expectedPowerType, uint32 expectedCreatedBySpellId);
HunterPetObservationStatus ObserveActiveOrdinaryHunterPetStatus(
    Player const* bot,
    HunterPetIdentitySnapshot& snapshot);
bool ObserveActiveOrdinaryHunterPet(Player const* bot,
    HunterPetIdentitySnapshot& snapshot);
}

#endif
