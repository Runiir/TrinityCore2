#ifndef TRINITY_BOT_NEFARIAN_NATIVE_OBSERVER_H
#define TRINITY_BOT_NEFARIAN_NATIVE_OBSERVER_H

// World-layer reader for BotNefarianNativeFacts.h. Include it only from the
// dispatch translation unit: it reads live units and spells and never
// changes them.

#include "Bots/BotSpellResolution.h"
#include "Bots/BotWorldPopulationMgrValidationRouteBoardingAction.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianCapabilities.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianFacts.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianNativeFacts.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianPickupMemory.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianTactics.h"
#include "GameObject.h"
#include "Map.h"
#include "Movement/Spline/MoveSpline.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Spell.h"
#include "SpellHistory.h"
#include "SpellInfo.h"
#include "Transport.h"

#include <mutex>

namespace BotEncounter::Nefarian
{
// The pickup memory is shared by every bot of the process (a damage dealer
// reads its tank's budget); the observer is its only writer.
inline PickupMemory& SharedPickupMemory()
{
    static PickupMemory memory;
    return memory;
}

inline std::mutex& SharedPickupMutex()
{
    static std::mutex mutex;
    return mutex;
}

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

    facts.Heroic = observer->GetMap() && observer->GetMap()->IsHeroic();
    for (ActorSnapshot const& player : board.Players)
        if (player.Guid != observer->GetGUID())
            if (Player const* member = ObjectAccessor::GetPlayer(*observer, player.Guid))
                if (member->IsInWorld() && observer->GetDistance(member) <= 45.0f
                    && !observer->IsWithinLOSInMap(member))
                    facts.OutOfSight.push_back(player.Guid);
    // The dragons too (round 7): the Onyxia tank's pickup needs the native
    // line of sight, not only the pillar model.
    for (auto const* list : { &board.Hostiles, &board.Summons })
        for (ActorSnapshot const& actor : *list)
            if (actor.Entry == OnyxiaEntry || actor.Entry == NefarianEntry)
                if (Unit const* dragon = ObjectAccessor::GetUnit(*observer, actor.Guid))
                    if (dragon->IsInWorld() && observer->GetDistance(dragon) <= 60.0f
                        && !observer->IsWithinLOSInMap(dragon))
                        facts.OutOfSight.push_back(actor.Guid);

    // The Onyxia pickup's memory: the tank records its own decisions (the
    // spot, whether it stands still and whether the native line of sight to
    // Onyxia holds); everyone reads the tank's budget.
    EncounterView const view = ObserveEncounter(board);
    if (view.OnyxiaAlive())
    {
        DutyPlan const duty = BuildNefarianDutyPlan(board);
        ObjectGuid const tank = OnyxiaTankNow(board, duty);
        if (!tank.IsEmpty())
        {
            std::lock_guard<std::mutex> lock(SharedPickupMutex());
            PickupState state;
            if (tank == observer->GetGUID())
                state = SharedPickupMemory().Observe(tank, view.Onyxia->Guid,
                    view.Onyxia->InCombat && view.Onyxia->VictimGuid != tank,
                    { observer->GetPositionX(), observer->GetPositionY(),
                        observer->GetPositionZ() },
                    !observer->movespline->Finalized(), facts.InSight(view.Onyxia->Guid),
                    board.ObservedAtMs);
            else
                state = SharedPickupMemory().Find(tank, view.Onyxia->Guid, board.ObservedAtMs);
            if (!state.Tank.IsEmpty())
                facts.Pickups.push_back(state);
        }
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
                TauntFor(player.ClassSpec).SpellId,
                WarriorRootFor(player.ClassSpec), OffHealFor(player.ClassSpec),
                PreAscentShieldFor(player.ClassSpec), PreAscentTopUpFor(player.ClassSpec) })
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
        bool const falling = BotValidationRouteBoardingAction::NativeFallInProgress(bot);
        bool const landing = BotValidationRouteBoardingAction::NativeFallLandingPending(bot);
        if (falling || landing)
            facts.Falls.push_back({ player.Guid, falling, landing });
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
