#ifndef TRINITY_BOT_ATRAMEDES_SOUND_BOUND_H
#define TRINITY_BOT_ATRAMEDES_SOUND_BOUND_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesFacts.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesObservationCounters.h"
#include <string_view>

// The kiter Sound bound (user decision 2026-09-30, "Bound kiter Sound"): in
// every air-phase Roaring Flame chase the tracked kiter stays at
// KiterSoundBound (10) Sound or less. run_sanity blocks a counted 10N kill on
// any chase sample above it (BotAtramedesObservationCounters.h). The native
// flame keeps its time-only speed ramp.
//
// A shield strike sets every Sound bar to 0 (77709), so three strikes keep
// the bound, each within the shield budget (BotAtramedesGongPolicy.h):
//   pre-liftoff reset    a ground strike in the last PreLiftoffResetMs before
//                        the published liftoff while anyone is above
//                        KiterSoundNoMargin. The air phase's first flame
//                        spawns on a random player, the tank included
//                        (ledger breath_initial_target_rule), and a chase
//                        that starts above the bound cannot be repaired;
//   Sound reset          the chased player, or the striker the flame is about
//                        to track, is above KiterSoundNoMargin: one breath
//                        tick would break the bound, so strike at once;
//   Sound-bound contact  the hits the chased player is about to take (a
//                        breath tick, fire patch ticks) would push it above
//                        the bound: strike, as for a catch.
// A Sonar Bomb (+20) breaks the bound from any Sound, so no strike helps
// against it: the kite path keeps the chased player out of bomb zones and
// fire patches instead (BotAtramedesKitePath.h).
namespace BotEncounter::Atramedes
{
// 10N Sound per hit (4.3.4 client rows; ledger client_spell_values).
inline constexpr uint32 BreathTickSound = 3;      // 78353 every 500 ms, 5 yd
inline constexpr uint32 FirePatchTickSound = 5;   // 78023 every 1 s, 3 yd
inline constexpr uint32 SonarBombSound = 20;      // 92553, 6 yd
inline constexpr float BreathTickSeconds = 0.5f;
inline constexpr float FirePatchTickSeconds = 1.0f;
// Above this, the next breath tick breaks the bound: no margin is left.
inline constexpr uint32 KiterSoundNoMargin = KiterSoundBound - BreathTickSound;
// A breath tick still reaches a kiter this far from the flame (position
// jitter between two snapshots), and a patch tick one this far from a patch.
inline constexpr float BreathReachYards = FlameBreathRadius + 0.5f;
inline constexpr float FirePatchReachYards = FirePatchRadius + 1.0f;
// The pre-liftoff reset window. A ground strike stuns Atramedes for 5 s
// (Vertigo) and his liftoff waits for it, then the flame spawns about 4 s
// later (ledger ground_air_phase_timestamps): nothing but the last Sonar
// Pulse disks can add Sound in between.
inline constexpr uint32 PreLiftoffResetMs = 4000;

// Fire patches whose next tick can reach `at` (each is its own +5).
inline uint32 FirePatchesReaching(Facts const& facts, Vector3 const& at)
{
    uint32 count = 0;
    for (ActorSnapshot const* patch : facts.FirePatches)
    {
        float const dx = patch->Position.X - at.X;
        float const dy = patch->Position.Y - at.Y;
        count += dx * dx + dy * dy <= FirePatchReachYards * FirePatchReachYards;
    }
    return count;
}

// The Sound `player` holds after the hits it is about to take: a breath tick
// when `breathNext`, and every fire patch in reach.
inline uint32 NextSound(Facts const& facts, ActorSnapshot const& player, bool breathNext)
{
    return SoundOf(player) + (breathNext ? BreathTickSound : 0)
        + FirePatchTickSound * FirePatchesReaching(facts, player.Position);
}

// Why the bound wants a strike now for `player` (the chased player, or the
// striker the flame will track next), or nothing.
inline std::string_view SoundBoundGong(Facts const& facts, ActorSnapshot const& player,
    bool breathNext)
{
    if (SoundOf(player) > KiterSoundNoMargin)
        return "air_kiter_sound_reset";
    if (NextSound(facts, player, breathNext) > KiterSoundBound)
        return "air_kiter_sound_bound";
    return {};
}

// The withheld reason of a Sound-bound strike the budget forbids.
inline std::string_view SoundBoundWithheld(std::string_view reason)
{
    return reason == "air_kiter_sound_reset" ? "air_kiter_sound_reset_at_reserve"
        : "air_kiter_sound_bound_at_reserve";
}

// The last seconds before the published liftoff, with anyone (the tank
// included: the air flame may take it) above KiterSoundNoMargin.
inline bool PreLiftoffSoundResetDue(Facts const& facts)
{
    return facts.CurrentPhase == Phase::Ground && facts.LiftoffInMs
        && *facts.LiftoffInMs <= PreLiftoffResetMs && facts.MaxSound > KiterSoundNoMargin;
}
}

#endif
