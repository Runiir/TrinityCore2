#ifndef TRINITY_INSTANCE_TRANSPORT_RELEASE_H
#define TRINITY_INSTANCE_TRANSPORT_RELEASE_H

// Releasing on a raid transport during an encounter (round 2, Blackwing
// Descent 10N, Nefarian's End elevator GO 207834).
//
// Player::RepopAtGraveyard revives a releasing player at 50% health when the
// player is a transport passenger (`|| GetTransport()`), then teleports the
// living player to the closest graveyard.  That clause exists for ships and
// zeppelins, where a corpse on a moving map transport cannot be recovered.
// In a raid it is not Blizzlike: a raider who dies on an elevator during a
// boss releases as a ghost at the graveyard and cannot re-enter while the
// encounter is in progress (Map::CannotEnter, CANNOT_ENTER_ZONE_IN_COMBAT).
// Vanilla TrinityCore instead teleports a human alive to the graveyard, and a
// headless bot, whose cross-map teleport out of a dungeon is refused unless it
// is an exact ghost release, stays alive in place: run 6bf52232 revived bots
// about 1,100 times on the Nefarian elevator.
//
// The release script detaches such a passenger once its body has become a
// ghost (the OnPlayerRepop hook at the end of BuildPlayerRepop, which every
// release path calls before RepopAtGraveyard), so RepopAtGraveyard sees no
// transport and takes the ordinary ghost path.  Only static
// GAMEOBJECT_TYPE_TRANSPORT elevators and platforms qualify (Nefarian's
// GO 207834): a corpse left on one stays where the body fell.  Anything else
// keeps the native clause: moving GAMEOBJECT_TYPE_MO_TRANSPORT ships,
// zeppelins and gunships (the Icecrown gunship encounter included), open
// world and dungeon transports, and raid elevators while no encounter is in
// progress.

namespace InstanceTransportRelease
{
struct Observation
{
    bool OnTransport = false;
    // The transport is a static GAMEOBJECT_TYPE_TRANSPORT (not a moving
    // GAMEOBJECT_TYPE_MO_TRANSPORT map transport).
    bool StaticElevator = false;
    bool RaidMap = false;
    bool EncounterInProgress = false;
};

// True when the releasing passenger must leave the transport as a ghost.
inline bool DetachBeforeGraveyard(Observation const& observation)
{
    return observation.OnTransport && observation.StaticElevator
        && observation.RaidMap && observation.EncounterInProgress;
}
}

#endif
