#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotAdmissionIdentityGenerated.h"
#include "Bots/BotCalibrationFixtureContractGenerated.h"
#include "Bots/BotClassSpecActionProfile.h"

#include "CharmInfo.h"
#include "CellImpl.h"
#include "Creature.h"
#include "Cryptography/CryptoHash.h"
#include "GameTime.h"
#include "GridNotifiersImpl.h"
#include "Log.h"
#include "Pet.h"
#include "Player.h"
#include "SpellAuras.h"
#include "SpellHistory.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "TemporarySummon.h"
#include "Unit.h"
#include "Util.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cctype>
#include <cmath>
#include <limits>
#include <sstream>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace
{
uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}
}
void BotWorldPopulationMgr::ResetCalibrationInitialResources(Player* bot,
    CalibrationMetrics& metrics)
{
    if (!bot)
        return;

    using namespace BotCalibrationFixtureContractGenerated;
    SpecContract const* contract = FindSpec(Cohort().CalibrationTargetSpec);
    metrics.InitialResourceSourceContract = ContentSha256;
    metrics.InitialPowerObservations.clear();
    metrics.InitialRunesRequired = false;
    metrics.InitialComboPointsRequired = false;
    metrics.InitialNeutralEclipseRequired = false;
    metrics.InitialPetResourceRequired = false;
    metrics.InitialPetResourceObserved = false;

    auto addPower = [&metrics](Unit* unit, char const* unitKind,
        Powers power, char const* name, uint32 exactNativeValue,
        bool maximum)
    {
        uint32 const maxNative = unit
            ? std::max<int32>(0, unit->GetMaxPower(power)) : 0;
        uint32 const expectedNative = maximum ? maxNative : exactNativeValue;
        // Player fixture resource initialization is server-owned and
        // non-certifying. A pet is already an active player-owned actor, so
        // its native post-summon resource is observed and never refilled here.
        if (unit && std::string_view(unitKind) != "pet")
            unit->SetPower(power, int32(expectedNative));
        uint32 const observedNative = unit ? unit->GetPower(power) : 0;
        auto displayValue = [power](uint32 value)
        {
            return power == POWER_RAGE || power == POWER_RUNIC_POWER
                ? value / 10 : value;
        };
        CalibrationMetrics::InitialPowerObservation observation;
        observation.PowerType = uint8(power);
        observation.UnitKind = unitKind;
        observation.UnitGuid = unit ? unit->GetGUID().GetCounter() : 0;
        observation.PowerName = name;
        observation.ExpectedNativeValue = expectedNative;
        observation.ExpectedDisplayValue = displayValue(expectedNative);
        observation.ObservedNativeValue = observedNative;
        observation.ObservedDisplayValue = displayValue(observedNative);
        observation.ObservedMaximumNativeValue = maxNative;
        observation.ExpectedMaximum = maximum;
        observation.MatchesContract = unit && maxNative
            && observedNative == expectedNative
            && (std::string_view(unitKind) != "pet"
                || unit->GetPowerType() == power);
        metrics.InitialPowerObservations.push_back(std::move(observation));
    };

    if (contract && contract->PowerOffset + contract->PowerCount
            <= PowerContracts.size())
        for (uint32 index = 0; index < contract->PowerCount; ++index)
        {
            PowerContract const& power =
                PowerContracts[contract->PowerOffset + index];
            Unit* unit = std::string_view(power.UnitKind) == "pet"
                ? static_cast<Unit*>(bot->GetPet())
                : static_cast<Unit*>(bot);
            addPower(unit, power.UnitKind, Powers(power.PowerType),
                power.Name, power.ExactNativeValue, power.Maximum);
        }

    if (contract && contract->RunesReadyMask)
    {
        bot->InitRunes();
        metrics.InitialRunesRequired = true;
        metrics.InitialExpectedRuneReadyMask = contract->RunesReadyMask;
        metrics.InitialObservedRuneReadyMask = bot->GetRunesState();
    }

    if (contract && contract->ComboPoints != 255)
    {
        bot->ClearComboPoints();
        metrics.InitialComboPointsRequired = true;
        metrics.InitialExpectedComboPoints = contract->ComboPoints;
        metrics.InitialObservedComboPoints = bot->GetComboPoints();
    }

    if (contract && contract->NeutralEclipse)
    {
        bot->RemoveAurasDueToSpell(48517);
        bot->RemoveAurasDueToSpell(48518);
        metrics.InitialNeutralEclipseRequired = true;
        metrics.InitialNeutralEclipseObserved =
            !bot->HasAura(48517) && !bot->HasAura(48518)
            && bot->GetPower(POWER_ECLIPSE) == 0;
    }

    bool const petResourceRequired = contract
        && contract->PetResourceRequired;
    metrics.InitialPetResourceRequired = petResourceRequired;
    metrics.InitialPetResourceObserved = !petResourceRequired
        || std::any_of(metrics.InitialPowerObservations.begin(),
            metrics.InitialPowerObservations.end(),
            [](CalibrationMetrics::InitialPowerObservation const& row)
            {
                return row.UnitKind == "pet" && row.MatchesContract;
            });

    metrics.InitialResourcesObservedAtMs = NowMs();
    metrics.InitialResourcesApplied = contract
        && !metrics.InitialPowerObservations.empty();
    metrics.InitialResourcesMatchContract = metrics.InitialResourcesApplied
        && std::all_of(metrics.InitialPowerObservations.begin(),
            metrics.InitialPowerObservations.end(),
            [](CalibrationMetrics::InitialPowerObservation const& row)
            {
                return row.MatchesContract;
            })
        && (!metrics.InitialRunesRequired
            || metrics.InitialObservedRuneReadyMask
                == metrics.InitialExpectedRuneReadyMask)
        && (!metrics.InitialComboPointsRequired
            || metrics.InitialObservedComboPoints
                == metrics.InitialExpectedComboPoints)
        && (!metrics.InitialNeutralEclipseRequired
            || metrics.InitialNeutralEclipseObserved)
        && (!metrics.InitialPetResourceRequired
            || metrics.InitialPetResourceObserved);

    std::vector<RaidRosterItemIdentity> initialGear;
    if (!ObserveEquippedGearIdentity(bot, initialGear,
            metrics.InitialGearManifestSha256))
        metrics.InitialResourcesMatchContract = false;
    metrics.LastObservedGearManifestSha256 =
        metrics.InitialGearManifestSha256;
    // The provisioning identity is the comparison baseline. Scored
    // continuity sampling begins exactly at the published t=0 edge.
    metrics.GearIdentitySampleCount = 0;
    metrics.FirstGearIdentityObservedAtMs = 0;
    metrics.LastGearIdentityObservedAtMs = 0;
}
