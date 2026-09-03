#ifndef TRINITY_BOT_CONTROLLER_ROUTE_HOLD_IDENTITY_SELECTOR_H
#define TRINITY_BOT_CONTROLLER_ROUTE_HOLD_IDENTITY_SELECTOR_H

#include "Bots/BotChainwielderOwnerCheckpoint.h"
#include "Bots/BotNativePathCheckpoint.h"
#include "Bots/BotProfileCombatRangeCheckpoint.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawTransferLaneCheckpoint.h"

#include <string_view>

namespace BotControllerRouteHoldIdentitySelector
{
struct AuthorityTriple
{
    std::string_view FixtureId;
    std::string_view SealSha256;
    std::string_view SourceCommit;
};

struct AuthorityCatalog
{
    AuthorityTriple ProfileCombatRange;
    AuthorityTriple NativePath;
    AuthorityTriple MagmawTransfer;
    AuthorityTriple Chainwielder;
};

inline AuthorityTriple Select(std::string_view heldFixtureId,
    AuthorityCatalog const& authorities)
{
    if (heldFixtureId == BotProfileCombatRangeCheckpoint::FixtureId)
        return authorities.ProfileCombatRange;
    if (heldFixtureId == BotNativePathCheckpoint::FixtureId)
        return authorities.NativePath;
    if (heldFixtureId
        == BotEncounter::MagmawTransferLaneCheckpoint::FixtureId)
        return authorities.MagmawTransfer;
    return authorities.Chainwielder;
}
}

#endif
