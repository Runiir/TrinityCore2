#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_RAID_CONSUMABLES_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_RAID_CONSUMABLES_H

#include <cstdint>
#include <string_view>

namespace BotWorldPopulationMgrRaidConsumables
{
struct Contract
{
    char const* ClassSpec = nullptr;
    uint32_t FlaskItemId = 0;
    uint32_t FlaskItemSpellId = 0;
    uint32_t FlaskAuraSpellId = 0;
    uint32_t FoodItemId = 0;
    uint32_t FoodItemSpellId = 0;
    uint32_t FoodAuraSpellId = 0;
    uint32_t PrepotItemId = 0;
    uint32_t PrepotItemSpellId = 0;
    uint32_t PrepotAuraSpellId = 0;
    uint32_t CombatPotionItemId = 0;
    uint32_t CombatPotionItemSpellId = 0;
    uint32_t CombatPotionAuraSpellId = 0;
};

// The pre-pull window is open only before the encounter: this bot and every
// living roster member are out of combat, and no wipe-recovery ride owns the
// route node. A native wake (Chimaeron: Finkle Einhorn's gossip) engages the
// raid before the boss node begins, and a recovery ride splits the raid
// across a transport. In either case the gate cannot complete, and holding the
// GCD, cast and target lanes would starve combat healing, damage and the
// ride's surface walk. The candidate stands down instead; the pull gate stays
// advisory.
inline bool PrepullWindowOpen(bool botInCombat, bool rosterMemberInCombat,
    bool recoveryRideEngaged)
{
    return !botInCombat && !rosterMemberInCombat && !recoveryRideEngaged;
}

inline bool PrepotStageReady(bool magmawOwnsNode, bool suppressOffense,
    std::string_view suppressReason)
{
    return !magmawOwnsNode || !suppressOffense
        || suppressReason == "prepull_pull_owner_wait";
}

template <typename Receipt>
bool ReceiptReady(Receipt const& receipt)
{
    return receipt.ItemId && receipt.SpellId && receipt.AuraSpellId
        && receipt.SuccessfulUseCount >= receipt.RequiredUses
        && receipt.NativeUseFinishedSuccessfully
        && !receipt.NativeUseAwaitingAura
        && receipt.FinishedAtMs >= receipt.SubmittedAtMs
        && receipt.PreUseItemCount > receipt.PostUseItemCount
        && receipt.AuraObservedAtMs && receipt.CooldownObserved;
}

Contract const* FindContract(std::string_view classSpec);
}

#endif
