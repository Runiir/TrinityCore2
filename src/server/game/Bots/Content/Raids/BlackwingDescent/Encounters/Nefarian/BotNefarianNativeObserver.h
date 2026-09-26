#ifndef TRINITY_BOT_NEFARIAN_NATIVE_OBSERVER_H
#define TRINITY_BOT_NEFARIAN_NATIVE_OBSERVER_H

// World-layer reader for BotNefarianNativeFacts.h. Include it only from the
// dispatch translation unit: it reads live units and spells and never
// changes them.

#include "Bots/BotSpellResolution.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianCapabilities.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianFacts.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianNativeFacts.h"
#include "GameObject.h"
#include "Movement/Spline/MoveSpline.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Spell.h"
#include "SpellHistory.h"
#include "SpellInfo.h"
#include "Transport.h"

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
        Player const* bot = ObjectAccessor::GetPlayer(*observer, player.Guid);
        if (!bot || !bot->IsInWorld())
            continue;
        // The spells the duties name: whether the bot knows each one (a spell
        // it lacks is unknown and not ready) and, if so, whether SpellHistory
        // has it ready.
        for (uint32 spellId : { InterruptFor(player.ClassSpec).SpellId,
                ControlFor(player.ClassSpec).SpellId,
                TauntFor(player.ClassSpec).SpellId })
        {
            if (!spellId)
                continue;
            BotSpellResolution::Resolved const resolved =
                BotSpellResolution::Resolve(bot, spellId);
            bool const known = resolved.Effective
                && (resolved.Effective != resolved.Requested || bot->HasSpell(spellId));
            facts.Readiness.push_back({ player.Guid, spellId, known
                && bot->GetSpellHistory()->IsReady(resolved.Effective), known });
        }
        if (bot->movespline->Initialized() && !bot->movespline->Finalized())
        {
            G3D::Vector3 end = bot->movespline->FinalDestination();
            if (bot->movespline->onTransport)
                if (TransportBase const* carrier = bot->GetDirectTransport())
                    carrier->CalculatePassengerPosition(end.x, end.y, end.z);
            facts.Motion.push_back({ player.Guid, true, { end.x, end.y, end.z } });
        }
        Unit const* unit = bot;
        if (!unit->GetTransport())
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
