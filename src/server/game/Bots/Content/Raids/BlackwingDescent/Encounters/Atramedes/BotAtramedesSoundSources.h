#ifndef TRINITY_BOT_ATRAMEDES_SOUND_SOURCES_H
#define TRINITY_BOT_ATRAMEDES_SOUND_SOURCES_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesGeometry.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesSoundBound.h"
#include <cmath>
#include <map>
#include <string>

// The source of every player's last Sound increment, for the acceptance
// observation's chase samples (round 4; live r03 batch 2 had a 20 Sound chase
// sample no log could explain: the combat log records no absorbed Sonar Bomb,
// and 20 is also four fire-patch ticks). Observation only: nothing here
// changes a decision.
//
// A snapshot shows a player's Sound bar, not the hit that raised it. When the
// bar rose since the player's last snapshot, the rise is attributed to every
// Sound source in reach of the player in the snapshot that shows it (joined
// by '+'), each only when the rise is at least that source's 10N hit:
//   sonar_bomb    a Sonar Bomb marker within 6 yd (+1.5), rise >= 20
//   sonic_breath  in the Sonic Breath cone (+10 degrees), rise >= 20
//   fire_patch    a fire patch whose tick reaches it, rise >= 5
//   roaring_flame a Reverberating Flame within 8 yd (+1.5; breath ticks +3
//                 within 5 yd, the spawn burst +10 within 8 yd)
//   sonar_pulse   a Sonar Pulse disk within 5 yd (+1.5), rise >= 3
// Nothing in reach: "unattributed". A player first seen with Sound:
// "before_observation" (the rise predates the sampling).
namespace BotEncounter::Atramedes
{
inline constexpr float SoundSourceSlackYards = 1.5f;
inline constexpr float FlameSpawnBurstYards = 8.0f;
inline constexpr float SonicBreathSourcePadRad = 10.0f * Geometry::Pi / 180.0f;

inline std::string SoundIncrementSource(Facts const& facts, ActorSnapshot const& player, uint32 rise)
{
    std::string sources;
    auto add = [&sources](char const* name)
    {
        if (!sources.empty())
            sources += '+';
        sources += name;
    };
    Vector3 const& at = player.Position;
    auto near = [&at](std::vector<ActorSnapshot const*> const& actors, float yards)
    {
        for (ActorSnapshot const* actor : actors)
            if (Geometry::Distance2d(actor->Position, at) <= yards)
                return true;
        return false;
    };
    if (rise >= SonarBombSound && near(facts.BombMarkers, SonarBombRadius + SoundSourceSlackYards))
        add("sonar_bomb");
    if (rise >= 20 && facts.SonicBreathActive && facts.Boss && !facts.TrackingFlames.empty())
    {
        float const beam = Geometry::Bearing(facts.Boss->Position, facts.TrackingFlames.front()->Position);
        float const offset = std::fabs(Geometry::AngleDelta(Geometry::Bearing(facts.Boss->Position, at), beam));
        if (offset <= SonicBreathHalfAngleRad + SonicBreathSourcePadRad)
            add("sonic_breath");
    }
    if (rise >= FirePatchTickSound && FirePatchesReaching(facts, at))
        add("fire_patch");
    if (near(facts.ReverberatingFlames, FlameSpawnBurstYards + SoundSourceSlackYards))
        add("roaring_flame");
    if (rise >= BreathTickSound && near(facts.SonarPulses, SonarPulseRadius + SoundSourceSlackYards))
        add("sonar_pulse");
    return sources.empty() ? std::string("unattributed") : sources;
}

// Every player's Sound and the source, size and time of its last rise, over
// the snapshots of one cohort attempt, in order.
class SoundSourceTracker
{
public:
    struct Last
    {
        uint32 Sound = 0;
        std::string Source;
        uint32 Increment = 0;
        uint64 AtMs = 0;
    };

    void Observe(Blackboard const& board, Facts const& facts)
    {
        for (ActorSnapshot const& player : board.Players)
        {
            uint32 const sound = SoundOf(player);
            auto const found = _players.find(player.Guid.GetRawValue());
            if (found == _players.end())
            {
                Last& first = _players[player.Guid.GetRawValue()];
                first.Sound = sound;
                if (sound)
                {
                    first.Source = "before_observation";
                    first.Increment = sound;
                    first.AtMs = board.ObservedAtMs;
                }
                continue;
            }
            Last& last = found->second;
            if (sound > last.Sound)
            {
                last.Increment = sound - last.Sound;
                last.Source = SoundIncrementSource(facts, player, last.Increment);
                last.AtMs = board.ObservedAtMs;
            }
            last.Sound = sound;
        }
    }

    Last const* Find(uint64 rawGuid) const
    {
        auto const found = _players.find(rawGuid);
        return found == _players.end() ? nullptr : &found->second;
    }

private:
    std::map<uint64, Last> _players;
};
}

#endif
