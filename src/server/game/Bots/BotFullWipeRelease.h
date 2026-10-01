#ifndef TRINITY_BOT_FULL_WIPE_RELEASE_H
#define TRINITY_BOT_FULL_WIPE_RELEASE_H

// Release gate after a native full wipe (Blackwing Descent 10N round 3,
// diag_r3 Q3/Q5, Nefarian).  Player::RepopAtGraveyard resurrects a released
// player on the spot, at half health, when the player stands on a transport,
// in a NoGhostOnRelease area or below the map's minimum height.  After the
// Nefarian phase-1 wipe every bot stood on the lair's transport: the full-wipe
// latch opened the release and all ten came back in the next world tick inside
// the still-engaged encounter, died again 30-40 s later (the death loop),
// merged a second attempt into the boss window and left the observer, whose
// reporter is a living bot, with a gap.
//
// A real raid ends the attempt at the wipe, lets the encounter reset, runs
// back and resurrects.  An in-place resurrection is no runback, so the
// recovery never releases into it: the attempt ends as a wipe, typed, and the
// shard watchdog stops the shard at its next heartbeat.  A release that makes a
// ghost keeps the existing native runback, ready check and re-pull.  Pure
// logic: the caller reads the engine's own three conditions.
namespace BotFullWipeRelease
{
constexpr char const* RevivesInPlaceReason = "native_full_wipe_release_revives_in_place";

inline bool ReleaseRevivesInPlace(bool onTransport, bool noGhostOnReleaseArea, bool belowMinHeight)
{
    return onTransport || noGhostOnReleaseArea || belowMinHeight;
}

// The terminal reason for a not-yet-released member, or nullptr to release.
// Only canonical raid cohorts (BotCanonicalRaidScope.h) under a pending
// native full-wipe recovery are gated.
inline char const* TerminalReason(bool canonicalRaid, bool fullWipeRecoveryPending,
    bool alreadyGhost, bool releaseRevivesInPlace)
{
    if (!canonicalRaid || !fullWipeRecoveryPending || alreadyGhost || !releaseRevivesInPlace)
        return nullptr;
    return RevivesInPlaceReason;
}
}

#endif
