#ifndef TRINITY_BOT_PET_AREA_GUARD_H
#define TRINITY_BOT_PET_AREA_GUARD_H

#include "Bots/BotProtectedTargetReach.h"
#include "Define.h"

#include <mutex>
#include <unordered_set>

class Player;
class SpellInfo;
class Unit;

// Protected-encounter guard for a commanded pet area spell (Blackwing Descent
// 10N round 3, diag_r3 Q2): the Felguard's Felstorm (89751) was commanded as
// soon as the pet stood in melee range of its drudge, and its whirl, centred
// on the PET, hit the Exposed Head of Magmaw 22-28 yards from Magmaw's centre
// on the drudge trash node in every batch.  The owner's own protected-target
// check is anchored on the owner or on the owner's target, never on the pet,
// so it could not see that.
//
// A pet area command is allowed only after a combat-reach-inclusive search
// around the pet itself, with the spell's own native area radius (triggered
// spells included) plus the distance the pet can follow its victim while it
// channels.  An unresolved radius fails closed to the 45-yard area guard.
//
// Scope: canonical-composition raid cohorts only (BotCanonicalRaidScope.h),
// set with the owner's route combat authority, so Stonecore, calibration and
// the legacy accepted Magmaw scenario keep their pet behaviour exactly.
namespace BotPetAreaGuard
{
struct ScopeRegistry
{
    std::mutex Lock;
    std::unordered_set<uint64> Owners;
};

inline ScopeRegistry& Scope()
{
    static ScopeRegistry registry;
    return registry;
}

inline void SetScoped(uint64 ownerGuid, bool scoped)
{
    if (!ownerGuid)
        return;
    ScopeRegistry& registry = Scope();
    std::lock_guard<std::mutex> guard(registry.Lock);
    if (scoped)
        registry.Owners.insert(ownerGuid);
    else
        registry.Owners.erase(ownerGuid);
}

inline bool IsScoped(uint64 ownerGuid)
{
    ScopeRegistry& registry = Scope();
    std::lock_guard<std::mutex> guard(registry.Lock);
    return registry.Owners.count(ownerGuid) != 0;
}

// Felstorm channels for 6 s while the pet keeps chasing its victim; one
// nominal melee range of travel keeps the scan a superset of the whirl.
constexpr float PetMovementSlack = BotProtectedTargetReach::NominalMeleeRange;

// Radius of the pet-centred, combat-reach-inclusive scan for a spell whose
// largest native area radius is spellRadius (<= 0: unresolved).
inline float CollectRadius(float spellRadius)
{
    if (!(spellRadius > 0.0f))
        return BotProtectedTargetReach::AreaGuardRadius;
    return spellRadius + PetMovementSlack;
}

// Engine query (BotWorldPopulationMgrSpellSemantics.cpp).  For a scoped
// owner: true when the owner holds protected encounter entries and a living
// protected creature is inside CollectRadius of the pet, and also when the
// owner, pet or spell is missing (fail closed).  An unscoped owner keeps the
// previous behaviour (false).
bool PetAreaSpellReachesProtectedTarget(Player* owner, Unit* pet, SpellInfo const* spellInfo);
}

#endif
