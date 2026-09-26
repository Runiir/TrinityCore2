#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_COMBAT_RESOLVER_ADMISSION_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_COMBAT_RESOLVER_ADMISSION_H

#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotRoleSaturationPolicy.h"
#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrRaidCooldownReservation.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawBalanceMushroomDuty.h"

#include <functional>
#include <string>
#include <vector>

// What ResolveProfileCombatAction shares with its candidate admission
// (BotWorldPopulationMgrCombatResolverAdmission.cpp). Each member is the
// resolver local of the same name: inputs by value or const reference, and
// the candidates, the action and the best-candidate pointers the admission
// updates by reference. The range lambdas are passed by reference
// (std::ref), so their captures and call results are the resolver's own.
struct BotWorldPopulationMgr::ProfileCombatAdmission
{
    Player* Bot;
    Unit* Target;
    std::string const& Role;
    BotClassSpecActionProfile const& Profile;
    bool RaidRotationScope;
    uint32 TargetEntry;
    bool SolarEclipse;
    BotEncounter::MagmawBalanceMushroomState const& MushroomState;
    RoleSaturationState const& Saturation;
    BotCombatPotionHealthOwner const& PotionHealthOwner;
    BotRaidCooldownReservation::RouteContext const& CooldownRoute;
    uint32 HostileCount;
    bool DensityOnly;
    uint32 ExcludedSpellId;
    bool AreaOnly;
    bool SelfCenteredOnly;
    bool ForbidArea;
    bool HostileTargetOnly;
    bool MovementCompatibleOnly;
    uint32 PolicyExcludedSpellId;
    uint32 ScopedAreaSpellId;
    uint32 ScopedAreaTargetEntry;
    std::function<float(BotActionCandidate const&, float)> EffectiveSpellMinRange;
    std::function<float(BotActionCandidate const&, float)> EffectiveSpellMaxRange;
    bool (*CandidatePreferred)(BotActionCandidate const&, BotActionCandidate const*);
    std::vector<BotActionCandidate>& Candidates;
    ResolvedCombatAction& Action;
    BotActionCandidate*& Best;
    BotActionCandidate*& BestInterrupt;
    BotActionCandidate*& BestDensityRecovery;
    BotActionCandidate*& BestDensityResourceFallback;
    BotActionCandidate*& BestDensityGenerator;
    BotActionCandidate*& BestDensityFallback;
    BotActionCandidate*& BestRangeRecovery;
    BotActionCandidate*& BestMagmawMushroomPlacement;
    BotActionCandidate*& BestMagmawMushroomDetonation;
};

#endif
