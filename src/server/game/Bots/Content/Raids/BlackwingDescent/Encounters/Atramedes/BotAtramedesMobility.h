#ifndef TRINITY_BOT_ATRAMEDES_MOBILITY_H
#define TRINITY_BOT_ATRAMEDES_MOBILITY_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesFacts.h"
#include <algorithm>
#include <array>
#include <optional>
#include <string_view>
#include <vector>

// Movement abilities of the canonical 10N roster that extend an air kite
// (user raid experience, 2026-09-25: "people who have mobility spells are
// better at gongs in the air phase because they can outrun the laser longer").
//
// Every number is the 4.3.4 client row (Spell.dbc, SpellEffect.dbc,
// SpellDuration.dbc, SpellCooldowns.dbc, SpellRadius.dbc):
//   Sprint 2983              aura 31 +70%, 8 s,  cooldown 60 s, off the GCD
//   Dash 1850                aura 31 +70%, 15 s, cooldown 180 s, Cat Form
//   Stampeding Roar 77764    aura 31 +60%, 8 s,  cooldown 120 s, Cat Form
//   Blink 1953               effect 29 LEAP 20 yd forward, cooldown 15 s
//   Disengage 781            effect 138 LEAP_BACK, 20 yd/s horizontal and
//                            7.5 yd/s vertical: 2 x 7.5 / 19.29111 (server
//                            gravity) x 20 = 15.55 yd back, cooldown 25 s
//   Ice Block 45438          10 s stun with immunity to every school
//                            (aura 39 misc 1 and 126), cooldown 300 s,
//                            Hypothermia 41425 (30 s) forbids a recast
//                            (BotAtramedesIceBlock.h)
//   Cat Form 768             instant shapeshift, needed by Dash and Roar
// Left out: Ghost Wolf 2645 has a 2 s cast, so it cannot help a kiter already
// chased. Aspect of the Cheetah 5118 (+30%, Dazed 15571 when struck) would
// fight the hunter's persistent Aspect of the Hawk self-buff
// (BotPersistentSelfBuffContract.h), which is re-cast in combat: GCDs spent
// back and forth, or a Dazed hunter without Hawk. Talents (Body and Soul,
// Speed of Light, ...) are not assumed.
//
// Readiness is a runtime fact, never assumed: the snapshot publishes, for
// each of these spells a bot knows, a player MechanicTimer {SpellId,
// RemainingMs = the longer of the cooldown left and, for a GCD-bound spell,
// the global cooldown left; 0 = ready} (Source GroupState). A spell with no
// published timer counts as unknown and is never used, so a strike held
// back for an extension never waits on a cast the server would reject.
namespace BotEncounter::Atramedes::Mobility
{
inline constexpr uint32 SprintSpell = 2983;
inline constexpr uint32 DashSpell = 1850;
inline constexpr uint32 StampedingRoarSpell = 77764;
inline constexpr uint32 BlinkSpell = 1953;
inline constexpr uint32 DisengageSpell = 781;
inline constexpr uint32 IceBlockSpell = IceBlockAura;
inline constexpr uint32 CatFormSpell = 768;

enum class Kind : uint8
{
    Speed,
    LeapForward,
    LeapBack
};

struct Ability
{
    uint32 SpellId = 0;
    Kind Type = Kind::Speed;
    float SpeedPct = 0.0f;
    float Yards = 0.0f;
    uint32 DurationMs = 0;
    uint32 CooldownMs = 0;
    uint32 RequiredForm = 0;
    std::string_view Name;
};

inline constexpr std::array<Ability, 5> Abilities{{
    { SprintSpell, Kind::Speed, 70.0f, 0.0f, 8000, 60000, 0, "sprint" },
    { DashSpell, Kind::Speed, 70.0f, 0.0f, 15000, 180000, CatFormSpell, "dash" },
    { StampedingRoarSpell, Kind::Speed, 60.0f, 0.0f, 8000, 120000, CatFormSpell,
        "stampeding_roar" },
    { BlinkSpell, Kind::LeapForward, 0.0f, 20.0f, 0, 15000, 0, "blink" },
    { DisengageSpell, Kind::LeapBack, 0.0f, 15.55f, 0, 25000, 0, "disengage" },
}};

// Unbuffed run speed of a player.
inline constexpr float BaseRunSpeed = 7.0f;
// A speed buff is scored over this window: about one catch cycle.
inline constexpr float ScoreHorizonSeconds = 8.0f;

inline MechanicTimerSnapshot const* SpellTimer(ActorSnapshot const& actor, uint32 spellId)
{
    return actor.FindMechanicTimer(spellId);
}

inline bool Knows(ActorSnapshot const& actor, uint32 spellId)
{
    return SpellTimer(actor, spellId) != nullptr;
}

inline bool Ready(ActorSnapshot const& actor, uint32 spellId)
{
    MechanicTimerSnapshot const* timer = SpellTimer(actor, spellId);
    return timer && timer->RemainingMs == 0;
}

inline Ability const* Find(uint32 spellId)
{
    for (Ability const& ability : Abilities)
        if (ability.SpellId == spellId)
            return &ability;
    return nullptr;
}

// Movement speed auras do not stack: the largest applies.
inline float RunSpeed(ActorSnapshot const& actor)
{
    float pct = 0.0f;
    for (Ability const& ability : Abilities)
        if (ability.Type == Kind::Speed && FindAura(actor, ability.SpellId))
            pct = std::max(pct, ability.SpeedPct);
    return BaseRunSpeed * (1.0f + pct / 100.0f);
}

// Yards an ability adds to a kite over ScoreHorizonSeconds.
inline float YardsGained(Ability const& ability)
{
    if (ability.Type != Kind::Speed)
        return ability.Yards;
    float const seconds = ability.DurationMs
        ? std::min(ScoreHorizonSeconds, float(ability.DurationMs) / 1000.0f)
        : ScoreHorizonSeconds;
    return BaseRunSpeed * ability.SpeedPct / 100.0f * seconds;
}

// A known ability whose form requirement can be met (Cat Form known).
inline bool Usable(ActorSnapshot const& actor, Ability const& ability)
{
    return Knows(actor, ability.SpellId)
        && (!ability.RequiredForm || FindAura(actor, ability.RequiredForm)
            || Knows(actor, ability.RequiredForm));
}

// Capability: what the player has, ready or not. Ranks the air gong team.
inline float CapabilityYards(ActorSnapshot const& actor)
{
    float yards = 0.0f;
    for (Ability const& ability : Abilities)
        if (Usable(actor, ability))
            yards += YardsGained(ability);
    return yards;
}

// What the player has ready now (a speed buff already running counts too).
inline float ReadyYards(ActorSnapshot const& actor)
{
    float yards = 0.0f;
    for (Ability const& ability : Abilities)
        if (Usable(actor, ability) && (Ready(actor, ability.SpellId)
                || (ability.Type == Kind::Speed && FindAura(actor, ability.SpellId))))
            yards += YardsGained(ability);
    return yards;
}

// Spec capability from the roster alone (the abilities each class of the
// canonical roster trains; no talents): ranks the air gong team when the
// snapshot publishes no spell timers, so the assignment never depends on
// what happens to be off cooldown.
inline float StaticCapabilityYards(std::string_view spec)
{
    auto has = [spec](std::string_view word)
    {
        return spec.find(word) != std::string_view::npos;
    };
    auto yards = [](uint32 spellId)
    {
        Ability const* ability = Find(spellId);
        return ability ? YardsGained(*ability) : 0.0f;
    };
    if (has("rogue"))
        return yards(SprintSpell);
    if (has("druid"))
        return yards(DashSpell) + yards(StampedingRoarSpell);
    if (has("hunter"))
        return yards(DisengageSpell);
    if (has("mage"))
        return yards(BlinkSpell);
    return 0.0f;
}

// Published capability when any timer is published, else the spec table.
inline float GongCapabilityYards(ActorSnapshot const& actor, bool published)
{
    return published ? CapabilityYards(actor) : StaticCapabilityYards(actor.ClassSpec);
}

inline bool AnyPublished(Blackboard const& board)
{
    for (ActorSnapshot const& player : board.Players)
        for (Ability const& ability : Abilities)
            if (Knows(player, ability.SpellId))
                return true;
    return false;
}

// The kite extensions a player could use now: known and ready (the
// published readiness includes the global cooldown of a GCD-bound spell),
// the required form active or its shapeshift ready too, and no faster speed
// buff already running. The choice among them depends on the chase
// (KiteExtension, BotAtramedesAirGong.h).
inline std::vector<Ability const*> ReadyAbilities(ActorSnapshot const& actor)
{
    std::vector<Ability const*> ready;
    float const running = RunSpeed(actor);
    for (Ability const& ability : Abilities)
    {
        if (!Usable(actor, ability) || !Ready(actor, ability.SpellId))
            continue;
        if (ability.RequiredForm && !FindAura(actor, ability.RequiredForm)
            && !Ready(actor, ability.RequiredForm))
            continue;
        if (ability.Type == Kind::Speed
            && BaseRunSpeed * (1.0f + ability.SpeedPct / 100.0f) <= running)
            continue;
        ready.push_back(&ability);
    }
    return ready;
}

// The use of an ability: the ability itself, or first Cat Form when it
// needs the form (the next decision then casts the ability).
struct Extension
{
    Ability const* Use = nullptr;
    uint32 CastSpellId = 0;
};

inline Extension ExtensionFor(ActorSnapshot const& actor, Ability const& ability)
{
    Extension extension;
    extension.Use = &ability;
    extension.CastSpellId = ability.RequiredForm && !FindAura(actor, ability.RequiredForm)
        ? ability.RequiredForm : ability.SpellId;
    return extension;
}
}

#endif
