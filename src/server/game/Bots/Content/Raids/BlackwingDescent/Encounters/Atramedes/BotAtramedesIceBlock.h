#ifndef TRINITY_BOT_ATRAMEDES_ICE_BLOCK_H
#define TRINITY_BOT_ATRAMEDES_ICE_BLOCK_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesGongPolicy.h"
#include <limits>
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
//           still ready: it holds still, still casting at the boss, while
//           the flame waits 2 s, flies to the shield and comes for it (the
//           survival Ice Block cast pre-empts the damage cast);
//   ice     the flame tracking it is inside IceBlockTriggerYards: Ice Block
//           (45438, 10 s, immune to every school, so no breath damage and no
//           Sound); it stays in place for the whole block;
//   exit    the block is over (Hypothermia 41425, the flame still following,
//           see UntrackedAirKiter): Blink (1953) away from the flame, then
//           an ordinary kite.
// Ice Block readiness comes only from the published cooldown (300 s) and the
// absence of Hypothermia; it is never assumed. It is also strictly once per
// fight: once an Ice Block was seen in the fight, it stays spent even when
// the cooldown comes back in a long fight (IceBlockUsable, the attempt-scoped
// memory in BotAtramedesIceBlockGuard.h). A pending global cooldown
// keeps the play going but delays the cast (IceBlockAvailable), and the
// chased mage waits for it only while it beats the breath: castable now, or
// ready before the predicted contact less a decision step (IceBlockInTime;
// else the rescue strike or the mage's mobility goes ahead); from the
// time the flame could reach the mage within one global cooldown, the bait
// stops casting at the boss so the block is castable when it arrives. Nitro Boots (an engineering
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

// Ice Block is on the global cooldown (4.3.4 SpellCooldowns 3200:
// StartRecoveryTime 1500), and its published readiness includes the global
// cooldown (AppendAtramedesPlayerSpellTimers). A mage casting at the boss is
// therefore "not ready" for up to 1.5 s after every cast start. The play
// decisions (who takes the rescue, the bait, the chased mage's own block)
// must not flicker with that: Ice Block counts as available while at most a
// global cooldown is left, and is cast only once it is ready.
inline constexpr uint32 IceBlockGlobalCooldownMs = 1500;

inline bool IceBlockAvailable(ActorSnapshot const& actor)
{
    if (!actor.Alive || !IsMageSpec(actor.ClassSpec)
        || FindAura(actor, HypothermiaAura) || IsIced(actor))
        return false;
    MechanicTimerSnapshot const* timer = Mobility::SpellTimer(actor, Mobility::IceBlockSpell);
    return timer && timer->RemainingMs <= IceBlockGlobalCooldownMs;
}

// Castable now: available and off the global cooldown too.
inline bool IceBlockReady(ActorSnapshot const& actor)
{
    return IceBlockAvailable(actor) && Mobility::Ready(actor, Mobility::IceBlockSpell);
}

// The plays' readiness: strictly once per fight, so an Ice Block the fight
// already used (Facts::IceBlockSpent, from IceBlockGuard) is never available
// again, whatever the cooldown says. Every play starts from these.
inline bool IceBlockUsable(Facts const& facts, ActorSnapshot const& actor)
{
    return !facts.IceBlockSpent && IceBlockAvailable(actor);
}

inline bool IceBlockCastable(Facts const& facts, ActorSnapshot const& actor)
{
    return !facts.IceBlockSpent && IceBlockReady(actor);
}

// A decision step of latency: the block goes out within this after it turns
// castable (the replays step the snapshot every 250 ms; the combat decision
// interval is 100 ms, BotSpellQueue.h).
inline constexpr float IceBlockLatencySeconds = 0.25f;

// Seconds until the chased mage's Ice Block can be cast (the published
// readiness: the cooldown or the global cooldown, whichever is longer); 0
// when it is castable now, infinity when it is no play this fight.
inline float IceBlockReadySeconds(Facts const& facts, ActorSnapshot const& actor)
{
    if (!IceBlockUsable(facts, actor))
        return std::numeric_limits<float>::infinity();
    MechanicTimerSnapshot const* timer = Mobility::SpellTimer(actor, Mobility::IceBlockSpell);
    return timer ? float(timer->RemainingMs) / 1000.0f : std::numeric_limits<float>::infinity();
}

// The chased mage's own block beats the breath: castable now, or ready at or
// before the predicted contact less a decision step. Anything later takes
// breath ticks (+3 Sound and 15-16k damage every 0.5 s) while it waits, so
// the rescue (or the mage's mobility) must not be held back for it.
inline bool IceBlockInTime(Facts const& facts, ActorSnapshot const& actor, float secondsToContact)
{
    float const ready = IceBlockReadySeconds(facts, actor);
    return ready <= 0.0f || ready + IceBlockLatencySeconds <= secondsToContact;
}

// The mage for the Ice Block rescue: the gong backup when it is a mage with
// Ice Block available, otherwise the lowest-GUID such mage (never the tank).
inline ActorSnapshot const* IceMage(Blackboard const& board, Facts const& facts,
    DutyPlan const& duties)
{
    if (ActorSnapshot const* backup = FindLivingPlayer(board, duties.GongBackup))
        if (backup->Guid != duties.Tank && IceBlockUsable(facts, *backup))
            return backup;
    ActorSnapshot const* best = nullptr;
    for (ActorSnapshot const& player : board.Players)
        if (player.Guid != duties.Tank && IceBlockUsable(facts, player)
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

// Bait stage: this mage struck last and still holds Ice Block for the flame
// (available: a global cooldown from its last cast at the boss does not end
// the bait).
inline bool IceBaiting(Blackboard const& board, Facts const& facts,
    ActorSnapshot const& self)
{
    if (facts.CurrentPhase != Phase::Air || facts.ReverberatingFlames.empty()
        || !IceBlockUsable(facts, self))
        return false;
    ActorSnapshot const* newest = NewestAirStriker(board);
    return newest && newest->Guid == self.Guid;
}
}

#endif
