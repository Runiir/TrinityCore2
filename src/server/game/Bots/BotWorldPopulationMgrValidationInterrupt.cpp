#include "Bots/BotWorldPopulationMgr.h"

#include "Player.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <algorithm>
#include <string>

bool BotWorldPopulationMgr::TryValidationRouteInterrupt(
    WorldBotState& state, Player* bot,
    BotRolePowerBreakdown const& power, BotProgressionStage stage,
    BotProgressionActivity activity, std::string& situation,
    std::string& action, Unit* interruptTarget, char const* context)
{
    if (Cohort().Config.ValidationRouteKind != "boss"
        || Cohort().Config.ValidationRouteMechanicProfile.find("interrupt") == std::string::npos
        || !bot
        || !interruptTarget
        || !interruptTarget->IsAlive()
        || !bot->IsValidAttackTarget(interruptTarget))
        return false;

    uint32 interruptSpell = SelectInterruptSpell(bot);
    if (!interruptSpell)
        return false;

    SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(interruptSpell);
    if (!spellInfo || !bot->IsWithinLOSInMap(interruptTarget))
        return false;

    float maxRange = std::max(5.0f, spellInfo->GetMaxRange(false));
    if (!bot->IsWithinDistInMap(interruptTarget, maxRange))
        return false;

    BossMechanicFeatures features = BuildBossMechanicFeatures(bot, interruptTarget);
    bool cast = TryCastCombatSpell(bot, interruptTarget, interruptSpell);
    if (!cast && !features.BossCasting)
        return false;

    std::string raw = BuildRawJson(bot, interruptTarget);
    std::string semantic = BuildSemanticJson(bot, interruptTarget, "dungeon_boss", &power, stage, activity);
    char const* eventName = cast && features.MustInterrupt ? "interrupt_success" : "validation_interrupt";
    char const* result = cast
        ? (features.MustInterrupt ? "ok" : "assigned_interrupt_probe")
        : "assigned_interrupt_cast_window_missed";
    RecordEvent(state, bot, eventName, interruptTarget, result, raw.c_str(), semantic.c_str(),
        features.InterruptPriority > 0.0f ? features.InterruptPriority : 1.0f,
        features.CastSpellId,
        interruptSpell);
    situation = "dungeon_boss";
    action = "validation_interrupt";
    state.TargetGuid = interruptTarget->GetGUID();
    state.WasInCombat = true;
    return true;
}

