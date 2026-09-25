#ifndef TRINITY_BOT_ATRAMEDES_ICE_BLOCK_H
#define TRINITY_BOT_ATRAMEDES_ICE_BLOCK_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesGongPolicy.h"
#include <optional>
#include <string_view>

// The mage Ice Block air rescue (user raid experience, 2026-09-25): "after
// the first acquire-target in the air phase, the mage waits until the
// targeted player can't run away any more because of the acquire-target's
// speed, then clicks. The acquire target moves onto the mage, then the mage
// Ice Blocks and waits the full duration in place. As soon as it gets out of
// the ice it uses Blink [and Nitro Boots with engineering]. ... It can do
// this only once per fight because of the Ice Block cooldown."
//
// Stages, all derived from the snapshot:
//   strike  the rescue is due (the kiter can no longer outrun the flame) and
//           a mage with Ice Block ready stands in reach of a shield: the
//           mage strikes instead of any other relay;
//   bait    the mage struck (newest Resonating Clash 78168) and Ice Block is
//           still ready: it holds still and stops casting while the flame
//           waits 2 s, flies to the shield and comes for it;
//   ice     the flame tracking it is inside IceBlockTriggerYards: Ice Block
//           (45438, 10 s, immune to every school, so no breath damage and no
//           Sound); it stays in place for the whole block;
//   exit    the block is over (Hypothermia 41425, the flame still following,
//           see UntrackedAirKiter): Blink (1953) away from the flame, then
//           an ordinary kite.
// Ice Block readiness comes only from the published cooldown (300 s) and the
// absence of Hypothermia; it is never assumed. Nitro Boots (an engineering
// tinker) is not modelled: bots have no engineering cooldowns.
namespace BotEncounter::Atramedes
{
inline constexpr float IceBlockTriggerYards = FlameBreathRadius + 3.0f;

inline bool IsMageSpec(std::string_view spec)
{
    return spec == "fire_mage" || spec == "frost_mage" || spec == "arcane_mage";
}

inline bool IsIced(ActorSnapshot const& actor)
{
    return FindAura(actor, IceBlockAura) != nullptr;
}

inline bool IceBlockReady(ActorSnapshot const& actor)
{
    return actor.Alive && IsMageSpec(actor.ClassSpec)
        && Mobility::Ready(actor, Mobility::IceBlockSpell)
        && !FindAura(actor, HypothermiaAura) && !IsIced(actor);
}

// The mage for the Ice Block rescue: the gong backup when it is a mage with
// Ice Block ready, otherwise the lowest-GUID such mage (never the tank).
inline ActorSnapshot const* IceMage(Blackboard const& board, DutyPlan const& duties)
{
    if (ActorSnapshot const* backup = FindLivingPlayer(board, duties.GongBackup))
        if (backup->Guid != duties.Tank && IceBlockReady(*backup))
            return backup;
    ActorSnapshot const* best = nullptr;
    for (ActorSnapshot const& player : board.Players)
        if (player.Guid != duties.Tank && IceBlockReady(player)
            && (!best || player.Guid < best->Guid))
            best = &player;
    return best;
}

// The newest air striker (Resonating Clash 78168 expiring last).
inline ActorSnapshot const* NewestAirStriker(Blackboard const& board)
{
    ActorSnapshot const* newest = nullptr;
    uint64 newestExpiry = 0;
    for (ActorSnapshot const& player : board.Players)
        if (player.Alive)
            if (AuraSnapshot const* clash = FindAura(player, AirClashAura))
                if (!newest || clash->ExpiresAtMs > newestExpiry)
                {
                    newest = &player;
                    newestExpiry = clash->ExpiresAtMs;
                }
    return newest;
}

// Bait stage: this mage struck last and still holds Ice Block for the flame.
inline bool IceBaiting(Blackboard const& board, Facts const& facts,
    ActorSnapshot const& self)
{
    if (facts.CurrentPhase != Phase::Air || facts.ReverberatingFlames.empty()
        || !IceBlockReady(self))
        return false;
    ActorSnapshot const* newest = NewestAirStriker(board);
    return newest && newest->Guid == self.Guid;
}
}

#endif
