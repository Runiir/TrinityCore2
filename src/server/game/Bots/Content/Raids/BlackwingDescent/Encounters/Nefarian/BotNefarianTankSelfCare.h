#ifndef TRINITY_BOT_NEFARIAN_TANK_SELF_CARE_H
#define TRINITY_BOT_NEFARIAN_TANK_SELF_CARE_H

// Round 8 (user raid experience 2026-09-26): with two healers the tanks take
// the healerless pillar and heal themselves under Shadowflame Barrage. The
// Blood DK puts Death Strike first while hurt; the Feral uses Frenzied
// Regeneration (after Enrage for rage when unglyphed) and Survival Instincts
// at the bottom. M provisions Enrage and Frenzied Regeneration. Their
// pillar interrupts come first: the plan returns an interrupt alone
// (ChooseActions), and self-care follows on the next decision.

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianTactics.h"
#include <vector>

namespace BotEncounter::Nefarian
{
constexpr float DeathStrikeBelowPct = 80.0f;
constexpr float EnrageBelowPct = 65.0f;
constexpr float FrenziedRegenerationBelowPct = 50.0f;          // glyphed
constexpr float UnglyphedRegenerationBelowPct = 60.0f;         // rage conversion
constexpr float SurvivalInstinctsBelowPct = 30.0f;

inline std::vector<HealDecision> DecideTankSelfCare(EncounterView const& view,
    DutyPlan const& plan, ActorSnapshot const& bot, NativeFacts const* facts)
{
    std::vector<HealDecision> decisions;
    Phase const phase = view.CurrentPhase;
    if (!bot.Alive || !plan.IsTank(bot.Guid)
        || (phase != Phase::PlatformAscent && phase != Phase::PlatformHold
            && phase != Phase::PlatformReturn))
        return decisions;
    auto usable = [&](uint32 spell)
    {
        return !facts || facts->SpellUsable(bot.Guid, spell);
    };
    if (bot.ClassSpec == "blood_death_knight")
    {
        if (bot.HealthPct < DeathStrikeBelowPct && usable(SpellDeathStrike))
            if (ActorSnapshot const* prototype = PillarPrototype(view, plan.PillarOf(bot.Guid));
                prototype && prototype->Alive)
                decisions.push_back({ prototype->Guid, SpellDeathStrike,
                    "tank_self_heal_death_strike" });
        return decisions;
    }
    if (bot.ClassSpec == "feral_druid_tank")
    {
        // With the canonical Glyph of Frenzied Regeneration it converts no
        // rage: it raises health to 30%, adds 30% maximum health and 30%
        // healing received - a floor for the bottom, and Enrage feeds nothing.
        // Without the glyph it converts up to 10 rage a second at 0.30% of
        // maximum health each for 20 s: Enrage first for the rage, and used
        // earlier, while there is health to protect.
        bool const glyphed = !facts || facts->FrenziedRegenerationGlyphed(bot.Guid);
        float const regenerationBelow = glyphed ? FrenziedRegenerationBelowPct
            : UnglyphedRegenerationBelowPct;
        if (bot.HealthPct < SurvivalInstinctsBelowPct && usable(SpellSurvivalInstincts))
            decisions.push_back({ bot.Guid, SpellSurvivalInstincts, "tank_self_heal_survival_instincts" });
        if (!glyphed && bot.HealthPct < EnrageBelowPct && usable(SpellEnrage)
            && usable(SpellFrenziedRegeneration))
            decisions.push_back({ bot.Guid, SpellEnrage, "tank_self_heal_enrage" });
        if (bot.HealthPct < regenerationBelow && usable(SpellFrenziedRegeneration))
            decisions.push_back({ bot.Guid, SpellFrenziedRegeneration,
                "tank_self_heal_frenzied_regeneration" });
    }
    return decisions;
}
}

#endif
