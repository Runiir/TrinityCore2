#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/BotRaidAreaAuthority.h"
#include "Creature.h"
#include "GameTime.h"
#include "Map.h"
#include "ObjectAccessor.h"
#include "Pet.h"
#include "Player.h"
#include "Spell.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <algorithm>
#include <chrono>
#include <vector>

namespace
{
bool SpellHasHostileMultiTargetSemantics(SpellInfo const* spellInfo, uint8 depth = 0)
{
    if (!spellInfo || depth > 4)
        return false;
    if (spellInfo->Id == 48505 || spellInfo->Id == 89751)
        return true;
    for (uint8 effectIndex = 0; effectIndex < MAX_SPELL_EFFECTS; ++effectIndex)
    {
        SpellEffectInfo const& effect = spellInfo->Effects[effectIndex];
        if (!effect.IsEffect())
            continue;
        if (!spellInfo->IsPositiveEffect(effectIndex)
            && (effect.ChainTarget > 1 || effect.IsTargetingArea()
                || effect.IsEffect(SPELL_EFFECT_PERSISTENT_AREA_AURA)
                || effect.IsAreaAuraEffect()))
            return true;
        if (effect.TriggerSpell
            && SpellHasHostileMultiTargetSemantics(
                sSpellMgr->GetSpellInfo(effect.TriggerSpell), depth + 1))
            return true;
    }
    return false;
}

bool IsNativeCombatObserved(Player const* bot, Unit const* target)
{
    return bot && target && (bot->IsInCombat() || target->IsInCombat());
}

uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}
}

void BotWorldPopulationMgr::ReconcileRaidAreaAutocasts(Player* bot, bool suppress) const
{
    if (!bot)
        return;
    BotRaidAreaAuthority::Set(bot->GetGUID().GetRawValue(), suppress);
    if (!suppress)
        return;

    for (Unit* controlled : bot->m_Controlled)
    {
        Creature* creature = controlled ? controlled->ToCreature() : nullptr;
        if (!creature)
            continue;
        std::vector<uint32> activeAreaSpells;
        for (CurrentSpellTypes spellType : { CURRENT_GENERIC_SPELL, CURRENT_CHANNELED_SPELL })
            if (Spell* current = controlled->GetCurrentSpell(spellType))
                if (SpellHasHostileMultiTargetSemantics(current->GetSpellInfo()))
                {
                    activeAreaSpells.push_back(current->GetSpellInfo()->Id);
                    controlled->InterruptSpell(spellType, false);
                }
        for (uint32 spellId : activeAreaSpells)
        {
            controlled->RemoveAura(spellId);
            controlled->RemoveDynObject(spellId);
        }
        std::vector<uint32> enabledAreaSpells;
        for (uint8 index = 0; index < creature->GetPetAutoSpellSize(); ++index)
            if (uint32 const spellId = creature->GetPetAutoSpellOnPos(index))
                if (SpellHasHostileMultiTargetSemantics(sSpellMgr->GetSpellInfo(spellId)))
                    enabledAreaSpells.push_back(spellId);
        for (uint32 spellId : enabledAreaSpells)
        {
            controlled->RemoveAura(spellId);
            controlled->RemoveDynObject(spellId);
        }
    }
}

bool BotWorldPopulationMgr::PrepareBossMechanicAction(
    WorldBotState& state, Player* bot, Unit* boundRouteTarget,
    BossMechanicActionResult& result)
{
    // A caller that already resolved an authoritative route focus must not be
    // retargeted by FindBossTarget through this bot's victim, a group victim,
    // or an unrelated nearby boss. Ordinary boss dispatch remains unchanged
    // when no target is bound.
    result.Target = boundRouteTarget ? boundRouteTarget : FindBossTarget(bot);
    if (!result.Target && !boundRouteTarget && !state.TargetGuid.IsEmpty())
        result.Target = ObjectAccessor::GetUnit(*bot, state.TargetGuid);
    if (!result.Target)
    {
        ReconcileRaidAreaAutocasts(bot, false);
        return false;
    }

    // A validation-route boss can be approached before the native boss
    // context reports in-combat. Treat only the declared route objective as
    // boss context here, so its typed mechanic contract remains the sole
    // combat authority during initial engagement.
    Creature const* routeCreature = result.Target->ToCreature();
    bool const routeDirectedBoss = Cohort().Config.ValidationRouteKind == "boss"
        && routeCreature
        && (routeCreature->GetEntry() == Cohort().Config.ValidationRouteTargetEntry
            || routeCreature->GetEntry() == Cohort().Config.ValidationRouteOpenerTargetEntry
            || std::find(Cohort().Config.ValidationRouteAlternateTargetEntries.begin(),
                Cohort().Config.ValidationRouteAlternateTargetEntries.end(), routeCreature->GetEntry())
                != Cohort().Config.ValidationRouteAlternateTargetEntries.end());
    if (boundRouteTarget && !routeDirectedBoss)
    {
        ReconcileRaidAreaAutocasts(bot, true);
        bot->InterruptNonMeleeSpells(false);
        SubmitMeleeAutoAttackIntent(state,
            BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
            BotMeleeAutoAttack::Owner::Mechanic,
            BotActionArbitration::Priority::Mechanic,
            "bound_route_target_without_boss_contract");
        if (Pet* pet = bot->GetPet())
            pet->AttackStop();
        for (Unit* controlled : bot->m_Controlled)
            if (controlled)
                controlled->AttackStop();
        result.Handled = true;
        result.Situation = bot->GetMap() && bot->GetMap()->IsRaid() ? "raid_boss" : "dungeon_boss";
        result.Action = "raid_target_not_declared_hold";
        result.Failure = true;
        return false;
    }
    if (!IsBossContext(bot, result.Target) && !routeDirectedBoss)
    {
        ReconcileRaidAreaAutocasts(bot, false);
        return false;
    }

    result.Handled = true;
    result.Situation = bot->GetMap() && bot->GetMap()->IsRaid() ? "raid_boss" : "dungeon_boss";
    result.Features = BuildBossMechanicFeatures(bot, result.Target);
    state.TargetGuid = result.Target->GetGUID();
    bool const nativeCombatObservedBeforeAction =
        IsNativeCombatObserved(bot, result.Target);
    if (state.LastRaidTankSwapWipeGeneration != Cohort().Raid.WipeGeneration)
    {
        state.LastRaidTankSwapTriggerKey.clear();
        state.LastRaidTankSwapWipeGeneration = Cohort().Raid.WipeGeneration;
    }
    if (result.Features.RaidEncounter && !state.WasInCombat
        && nativeCombatObservedBeforeAction)
    {
        ++state.RaidAttempts;
        state.LastRaidTankSwapTriggerKey.clear();
        state.LastRaidTankSwapMs = NowMs();
        state.WasInCombat = true;
    }
    return true;
}
