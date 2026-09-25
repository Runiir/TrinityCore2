#ifndef TRINITY_BOT_NEFARIAN_NATIVE_OBSERVER_H
#define TRINITY_BOT_NEFARIAN_NATIVE_OBSERVER_H

// World-layer reader for BotNefarianNativeFacts.h. Include it only from the
// dispatch translation unit: it reads live units and spells and never
// changes them.

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianFacts.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianNativeFacts.h"
#include "GameObject.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Spell.h"
#include "SpellInfo.h"

namespace BotEncounter::Nefarian
{
inline NativeFacts ObserveNativeFacts(Player const* observer,
    Blackboard const& board)
{
    NativeFacts facts;
    if (!observer || !observer->IsInWorld()
        || board.Route.NodeId != EncounterNodeId)
        return facts;

    for (auto const* list : { &board.Hostiles, &board.Summons })
        for (ActorSnapshot const& actor : *list)
        {
            if (actor.Entry != PrototypeEntry || !actor.Cast
                || !IsBlastNova(actor.Cast->SpellId))
                continue;
            Unit const* unit = ObjectAccessor::GetUnit(*observer, actor.Guid);
            Spell const* spell = unit
                ? unit->GetCurrentSpell(CURRENT_GENERIC_SPELL) : nullptr;
            if (!spell || !spell->GetSpellInfo()
                || !IsBlastNova(spell->GetSpellInfo()->Id))
                continue;
            facts.Casts.push_back({ actor.Guid, spell->GetSpellInfo()->Id,
                spell->GetCastTime(), spell->GetRemainingCastTime() });
        }

    for (ActorSnapshot const& player : board.Players)
    {
        Unit const* unit = ObjectAccessor::GetUnit(*observer, player.Guid);
        if (!unit || !unit->GetTransport())
            continue;
        TransportPlacement placement;
        placement.Actor = player.Guid;
        placement.Transport = unit->GetTransGUID();
        if (GameObject const* transport =
                ObjectAccessor::GetGameObject(*observer, placement.Transport))
            placement.TransportEntry = transport->GetEntry();
        placement.Offset = { unit->GetTransOffsetX(), unit->GetTransOffsetY(),
            unit->GetTransOffsetZ() };
        facts.Placements.push_back(placement);
    }
    return facts;
}
}

#endif
