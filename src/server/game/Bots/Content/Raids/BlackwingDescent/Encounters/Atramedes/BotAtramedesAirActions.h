#ifndef TRINITY_BOT_ATRAMEDES_AIR_ACTIONS_H
#define TRINITY_BOT_ATRAMEDES_AIR_ACTIONS_H

#include "Bots/BotNativeActionIntent.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesMovementPolicy.h"
#include <optional>
#include <string_view>

// Per-bot air abilities: the chased player's kite extension (a speed buff,
// Cat Form for Dash or Stampeding Roar, Blink, Disengage), the chased mage's
// own Ice Block, and the Ice Block rescuer's bait and block
// (BotAtramedesIceBlock.h). Each is a native player cast; the strategy
// submits it as the plan's interaction.
namespace BotEncounter::Atramedes
{
struct AirAbility
{
    // The cast (CastSpell, or DirectionalMobility for a leap).
    std::optional<BotNativeAction::Intent> Cast;
    std::string_view Mechanic;
    // Movement this tick: none while holding still or leaping; a kite step
    // that leaves the cast lanes free beside an instant self-buff.
    bool Hold = false;
    bool KeepKiting = false;
    bool SuppressOffense = false;
    std::string_view SuppressReason;
};

inline BotNativeAction::Intent SelfCast(uint32 spellId)
{
    return BotNativeAction::CastSpell{ ObjectGuid(), spellId };
}

// The leap target: the next ring waypoint away from the flame (Blink goes
// forward toward it, Disengage faces the flame and leaps back toward it).
inline std::optional<BotNativeAction::Intent> LeapAway(Facts const& facts,
    ActorSnapshot const& self, Mobility::Ability const& leap, std::string_view reason)
{
    std::optional<Vector3> const next = NextRingWaypoint(self.Position,
        AirKiteDirection(facts, self));
    if (!next)
        return std::nullopt;
    BotNativeAction::DirectionalMobility mobility;
    mobility.X = next->X;
    mobility.Y = next->Y;
    mobility.Z = ArenaCenter.Z;
    mobility.SpellId = leap.SpellId;
    mobility.Facing = leap.Type == Mobility::Kind::LeapBack
        ? BotNativeAction::DirectionalMobilityFacing::Backward
        : BotNativeAction::DirectionalMobilityFacing::Forward;
    mobility.IntentReason = std::string(reason);
    return BotNativeAction::Intent(mobility);
}

// The kiter's move this tick when the gong decision held the strike back for
// its own mobility ("kiter_mobility_extension") or its own Ice Block.
inline std::optional<AirAbility> KiterAbility(Facts const& facts, ActorSnapshot const& self,
    std::string_view withheld)
{
    if (self.Guid != facts.AirKiter)
        return std::nullopt;
    ActorSnapshot const* flame = KiterFlame(facts, self);
    if (!flame)
        return std::nullopt;
    AirAbility ability;
    if (withheld == "kiter_ice_block")
    {
        ability.Cast = SelfCast(Mobility::IceBlockSpell);
        ability.Mechanic = "kiter_ice_block";
        ability.Hold = true;
        return ability;
    }
    // Speed buffs come before contact too, so the extension is the kiter's
    // own reading of the chase; at contact the gong decision holds the
    // strike back for the same extension ("kiter_mobility_extension").
    (void)withheld;
    std::optional<Mobility::Extension> const extension =
        KiteExtension(*flame, self, FlameTimeToContact(*flame, self));
    if (!extension)
        return std::nullopt;
    Mobility::Ability const& use = *extension->Use;
    ability.Mechanic = use.Name;
    if (extension->CastSpellId == use.SpellId && use.Type != Mobility::Kind::Speed)
    {
        ability.Cast = LeapAway(facts, self, use, use.Name);
        ability.Hold = true;
        return ability.Cast ? std::optional<AirAbility>(ability) : std::nullopt;
    }
    if (extension->CastSpellId != use.SpellId)
        ability.Mechanic = "cat_form_for_mobility";
    ability.Cast = SelfCast(extension->CastSpellId);
    ability.KeepKiting = true;
    return ability;
}

// The Ice Block rescuer after its strike: hold still, still casting at the
// boss, while the flame comes (the survival Ice Block cast pre-empts the
// damage cast); block once the flame tracking it is close; stay blocked.
inline std::optional<AirAbility> IceRescuerAbility(Blackboard const& board,
    Facts const& facts, ActorSnapshot const& self)
{
    AirAbility ability;
    ability.Hold = true;
    if (IsIced(self))
    {
        ability.Mechanic = "ice_block_hold";
        ability.SuppressOffense = true;
        ability.SuppressReason = "atramedes_ice_block";
        return ability;
    }
    if (!IceBaiting(board, facts, self))
        return std::nullopt;
    ability.Mechanic = "ice_block_bait";
    if (facts.AirKiter == self.Guid && !facts.AirKiterUntracked)
        if (ActorSnapshot const* flame = KiterFlame(facts, self))
            if (Geometry::Distance2d(flame->Position, self.Position) <= IceBlockTriggerYards)
            {
                ability.Cast = SelfCast(Mobility::IceBlockSpell);
                ability.Mechanic = "ice_block";
            }
    return ability;
}
}

#endif
