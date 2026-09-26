#ifndef TRINITY_BOT_RAID_SHAMAN_TOTEMS_H
#define TRINITY_BOT_RAID_SHAMAN_TOTEMS_H

#include "Define.h"

// Raid air-totem choice for a non-Elemental shaman (round 4).
//
// TryEnsureCombatTotems drops Wrath of Air (5% spell haste) for Elemental and
// Windfury (10% melee and ranged haste) for every other spec. In a raid the
// melee-haste category may already be covered by another member: Hunting
// Party 53290 (Survival hunter) and Improved Icy Talons 55610 (Death Knight)
// are raid area auras (SpellEffect 65, auras 319/320, 10%) that do not stack
// with Windfury. Then Windfury adds nothing and Wrath of Air is the raid's
// only 5% spell-haste source (the canonical BWD roster, Survival hunter plus a
// Restoration shaman on three-healer bosses). Raid scope only: dungeon and
// calibration shamans, and the legacy accepted Magmaw Elemental, keep today's
// choice.
namespace BotRaidShamanTotems
{
inline constexpr uint32 WrathOfAirTotem = 3738;
inline constexpr uint32 WindfuryTotem = 8512;
inline constexpr uint32 OtherMeleeHasteProviders[] = { 53290, 55610 };

// The provider probe walks the group, so it runs only for a raid non-Elemental
// shaman that knows Wrath of Air.
template <typename ProviderProbe>
bool PreferWrathOfAir(bool raidScope, bool isElemental, bool knowsWrathOfAir,
    ProviderProbe&& otherMeleeHasteProvider)
{
    return raidScope && !isElemental && knowsWrathOfAir && otherMeleeHasteProvider();
}
}

#endif
