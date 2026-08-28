#include "Bots/BotWorldPopulationMgrRaidConsumables.h"

#include "Bots/BotCalibrationFixtureContractGenerated.h"

#include <array>

namespace BotWorldPopulationMgrRaidConsumables
{
namespace
{
Contract IntellectContract(char const* classSpec)
{
    return { classSpec, 58086, 79470, 79470, 62671, 87587, 87547,
        58091, 79476, 79476, 58091, 79476, 79476 };
}

Contract AgilityContract(char const* classSpec)
{
    return { classSpec, 58087, 79471, 79471, 62669, 87586, 87546,
        58145, 79633, 79633, 58145, 79633, 79633 };
}

Contract StrengthContract(char const* classSpec)
{
    return { classSpec, 58088, 79472, 79472, 62670, 87584, 87545,
        58146, 79634, 79634, 58146, 79634, 79634 };
}

std::array<Contract,
    BotCalibrationFixtureContractGenerated::SpecContracts.size()>
BuildGeneratedContracts()
{
    std::array<Contract,
        BotCalibrationFixtureContractGenerated::SpecContracts.size()> result{};
    for (size_t index = 0; index < result.size(); ++index)
    {
        BotCalibrationFixtureContractGenerated::SpecContract const& source =
            BotCalibrationFixtureContractGenerated::SpecContracts[index];
        result[index] = {
            source.Spec,
            source.FlaskItemId,
            source.FlaskItemSpellId,
            source.FlaskAuraSpellId,
            source.FoodItemId,
            source.FoodItemSpellId,
            source.FoodAuraSpellId,
            source.PrepotItemId,
            source.PrepotItemSpellId,
            source.PrepotAuraSpellId,
            source.CombatPotionItemId,
            source.CombatPotionItemSpellId,
            source.CombatPotionAuraSpellId,
        };
    }
    return result;
}

std::array<Contract, 9> const& FallbackContracts()
{
    static std::array<Contract, 9> const contracts = {{
        StrengthContract("blood_death_knight"),
        StrengthContract("protection_paladin"),
        IntellectContract("holy_paladin"),
        IntellectContract("discipline_priest"),
        IntellectContract("restoration_shaman"),
        IntellectContract("restoration_druid"),
        IntellectContract("holy_priest"),
        AgilityContract("feral_druid_tank"),
        StrengthContract("frost_death_knight"),
    }};
    return contracts;
}
}

Contract const* FindContract(std::string_view classSpec)
{
    // Generated simulator contracts are the source of truth for every DPS
    // spec. Runtime-only tank/healer rows are explicit exact-spec fallbacks.
    static std::array<Contract,
        BotCalibrationFixtureContractGenerated::SpecContracts.size()> const
        generated = BuildGeneratedContracts();
    if (BotCalibrationFixtureContractGenerated::FindSpec(classSpec))
        for (Contract const& contract : generated)
            if (classSpec == contract.ClassSpec)
                return &contract;

    for (Contract const& contract : FallbackContracts())
        if (classSpec == contract.ClassSpec)
            return &contract;
    return nullptr;
}
}
