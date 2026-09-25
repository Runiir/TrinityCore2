#ifndef TRINITY_BOT_MALORIAK_NATIVE_TIMERS_H
#define TRINITY_BOT_MALORIAK_NATIVE_TIMERS_H

class WorldObject;

namespace BotEncounter
{
struct Blackboard;

// Publication pass for the cohort blackboard: on the Maloriak encounter
// node, copies boss_maloriak.cpp's read-only GetTimeUntilEncounterMechanic
// values (Maloriak::PublishedMechanicSpells) into the boss actor's
// MechanicTimers. Leaves every other node, boss and actor untouched.
// `observer` is the bot whose map built the snapshot.
void AppendMaloriakMechanicTimers(Blackboard& snapshot, WorldObject const& observer);
}

#endif
