#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotEncounterBlackboard.h"

#include "CellImpl.h"
#include "Creature.h"
#include "GameObject.h"
#include "GridNotifiersImpl.h"
#include "Map.h"
#include "Player.h"
#include "Spell.h"
#include "SpellInfo.h"
#include "Unit.h"

#include <algorithm>
#include <memory>
#include <set>
#include <utility>
#include <vector>
void BotWorldPopulationMgr::PublishEncounterBlackboard(uint64 nowMs)
{
    // The encounter view is a cohort observation, not per-bot perception.
    // Keep it immutable for the entire decision slice so one candidate cannot
    // erase or retarget facts that a later candidate still needs.
    if (Cohort().EncounterSnapshot && nowMs < Cohort().EncounterSnapshotNextRefreshMs)
        return;

    Player* observer = nullptr;
    for (WorldBotState const& state : Party().Bots)
    {
        Player* candidate = GetLoadedBot(state);
        if (candidate && candidate->IsInWorld())
        {
            observer = candidate;
            break;
        }
    }

    if (!observer)
    {
        Cohort().EncounterSnapshot.reset();
        Cohort().EncounterSnapshotNextRefreshMs = nowMs + 100;
        return;
    }

    auto snapshot = std::make_shared<BotEncounter::Blackboard>();
    snapshot->Revision = ++Cohort().EncounterSnapshotRevision;
    snapshot->ObservedAtMs = nowMs;
    snapshot->CurrentScope.CohortId = Cohort().Id;
    snapshot->CurrentScope.AttemptId = Cohort().AttemptId;
    snapshot->CurrentScope.WipeGeneration = uint32(Cohort().Raid.WipeGeneration);
    snapshot->CurrentScope.RouteGeneration = Party().ValidationRouteGeneration;
    snapshot->CurrentScope.NodeId = Cohort().Config.ValidationRouteNodeId;
    snapshot->CurrentScope.MapId = observer->GetMapId();
    snapshot->CurrentScope.InstanceId = observer->GetInstanceId();
    snapshot->CurrentScope.EncounterId = Cohort().Config.ValidationRouteMechanicProfile.empty()
        ? Cohort().Config.ValidationRouteKind
        : Cohort().Config.ValidationRouteMechanicProfile;
    snapshot->NativeBossState = Cohort().Raid.EncounterInProgress ? "in_progress" : "not_in_progress";

    snapshot->Route.NodeId = Cohort().Config.ValidationRouteNodeId;
    snapshot->Route.Kind = Cohort().Config.ValidationRouteNodeKind.empty()
        ? Cohort().Config.ValidationRouteKind
        : Cohort().Config.ValidationRouteNodeKind;
    snapshot->Route.Label = Cohort().Config.ValidationRouteLabel;
    snapshot->Route.MechanicProfile = Cohort().Config.ValidationRouteMechanicProfile;
    snapshot->Route.HazardSourceEntry = Cohort().Config.ValidationRouteHazardSourceEntry;
    snapshot->Route.HazardDetectionSpellId = Cohort().Config.ValidationRouteHazardDetectionSpellId;
    snapshot->Route.HazardRadius = Cohort().Config.ValidationRouteHazardRadiusYards;
    snapshot->Route.HazardSafetyMargin = Cohort().Config.ValidationRouteHazardSafetyMarginYards;
    snapshot->Route.MinimumDistance = Cohort().Config.ValidationRouteMinimumDistanceYards;
    if (Party().ValidationRouteManifestIndex < Party().ValidationRouteManifest.size())
    {
        ValidationRouteManifestNode const& routeNode =
            Party().ValidationRouteManifest[Party().ValidationRouteManifestIndex];
        snapshot->Route.InteractionAction = routeNode.NativeInteractionAction;
        snapshot->Route.InteractionEntry = routeNode.NativeInteractionEntry;
        snapshot->Route.InteractionMenus = routeNode.NativeInteractionMenus;
        snapshot->Route.InteractionOption = routeNode.NativeInteractionOption;
        snapshot->Route.CompletionKind = routeNode.NativeCompletionKind;
        snapshot->Route.CompletionEntry = routeNode.NativeCompletionEntry;
        snapshot->Route.CompletionSpellId = routeNode.NativeCompletionSpellId;
    }
    snapshot->Route.Complete = Party().ValidationRouteManifestComplete;
    snapshot->Route.NavigationHints.push_back({ Cohort().Config.ValidationRouteX,
        Cohort().Config.ValidationRouteY, Cohort().Config.ValidationRouteZ });
    auto appendEntries = [&snapshot](std::vector<uint32> const& entries)
    {
        snapshot->Route.AllowedEntries.insert(snapshot->Route.AllowedEntries.end(), entries.begin(), entries.end());
    };
    if (Cohort().Config.ValidationRouteTargetEntry)
        snapshot->Route.AllowedEntries.push_back(Cohort().Config.ValidationRouteTargetEntry);
    appendEntries(Cohort().Config.ValidationRouteAlternateTargetEntries);
    appendEntries(Cohort().Config.ValidationRouteAddTargetEntries);
    appendEntries(Cohort().Config.ValidationRoutePackTargetEntries);
    appendEntries(Cohort().Config.ValidationRouteScriptedEventEntries);
    std::sort(snapshot->Route.AllowedEntries.begin(), snapshot->Route.AllowedEntries.end());
    snapshot->Route.AllowedEntries.erase(std::unique(snapshot->Route.AllowedEntries.begin(),
        snapshot->Route.AllowedEntries.end()), snapshot->Route.AllowedEntries.end());

    auto buildUnit = [nowMs](Unit* unit, BotEncounter::ActorKind kind)
    {
        BotEncounter::ActorSnapshot actor;
        actor.Guid = unit->GetGUID();
        actor.Entry = unit->GetEntry();
        actor.Kind = kind;
        actor.Position = { unit->GetPositionX(), unit->GetPositionY(), unit->GetPositionZ() };
        actor.Facing = unit->GetOrientation();
        actor.Health = unit->GetHealth();
        actor.MaxHealth = unit->GetMaxHealth();
        actor.AlternatePower = unit->GetPower(POWER_ALTERNATE_POWER);
        actor.MaxAlternatePower = unit->GetMaxPower(POWER_ALTERNATE_POWER);
        actor.HealthPct = unit->GetMaxHealth() ? 100.0f * float(unit->GetHealth()) / float(unit->GetMaxHealth()) : 0.0f;
        actor.Alive = unit->IsAlive();
        actor.Attackable = unit->IsAlive() && !unit->HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_NOT_SELECTABLE);
        actor.Selectable = !unit->HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_NOT_SELECTABLE);
        actor.InCombat = unit->IsInCombat();
        actor.Flying = unit->IsFlying();
        actor.ReactAggressive = unit->ToCreature()
            && unit->ToCreature()->GetReactState() == REACT_AGGRESSIVE;
        actor.Interactable = unit->ToCreature()
            && (unit->ToCreature()->GetUInt32Value(UNIT_NPC_FLAGS) != 0
                || unit->ToCreature()->HasFlag(UNIT_NPC_FLAGS,
                    UNIT_NPC_FLAG_SPELLCLICK));
        actor.VictimGuid = unit->GetVictim() ? unit->GetVictim()->GetGUID() : ObjectGuid::Empty;
        actor.VehicleGuid = unit->GetVehicleBase() ? unit->GetVehicleBase()->GetGUID() : ObjectGuid::Empty;

        for (auto const& [_, application] : unit->GetAppliedAuras())
        {
            Aura const* aura = application ? application->GetBase() : nullptr;
            if (!aura)
                continue;
            BotEncounter::AuraSnapshot auraSnapshot;
            auraSnapshot.SpellId = aura->GetId();
            auraSnapshot.CasterGuid = aura->GetCasterGUID();
            auraSnapshot.Stacks = aura->GetStackAmount();
            auraSnapshot.ExpiresAtMs = aura->GetDuration() > 0 ? nowMs + uint64(aura->GetDuration()) : 0;
            actor.Auras.push_back(auraSnapshot);
        }

        for (CurrentSpellTypes spellType : { CURRENT_GENERIC_SPELL, CURRENT_CHANNELED_SPELL })
        {
            Spell* spell = unit->GetCurrentSpell(spellType);
            SpellInfo const* spellInfo = spell ? spell->GetSpellInfo() : nullptr;
            if (!spellInfo)
                continue;
            BotEncounter::CastSnapshot cast;
            cast.SpellId = spellInfo->Id;
            cast.TargetGuid = spell->m_targets.GetUnitTargetGUID();
            cast.ObservedAtMs = nowMs;
            cast.Channeled = spellType == CURRENT_CHANNELED_SPELL;
            cast.Interruptible = spellInfo->CanBeInterrupted(unit, false);
            actor.Cast = cast;
            break;
        }
        return actor;
    };

    std::set<ObjectGuid> seenUnits;
    for (WorldBotState const& state : Party().Bots)
    {
        Player* bot = GetLoadedBot(state);
        if (!bot || !bot->IsInWorld() || bot->GetMap() != observer->GetMap())
            continue;
        BotEncounter::ActorSnapshot player = buildUnit(bot, BotEncounter::ActorKind::Player);
        player.Role = GetDungeonRole(bot);
        snapshot->Players.push_back(std::move(player));
        seenUnits.insert(bot->GetGUID());

        BotEncounter::TargetChannels channels;
        channels.DamageTarget = state.TargetGuid;
        channels.MechanicTarget = Party().ValidationRouteFocusGuid;
        auto roster = Cohort().Raid.RosterByGuid.find(bot->GetGUID().GetCounter());
        if (roster != Cohort().Raid.RosterByGuid.end() && roster->second.Role == "tank")
            channels.TankAssignment = state.TargetGuid;
        snapshot->BotTargets.emplace(bot->GetGUID(), channels);

        for (Unit* controlled : bot->m_Controlled)
        {
            if (!controlled || !controlled->IsInWorld() || controlled->GetMap() != observer->GetMap()
                || !seenUnits.insert(controlled->GetGUID()).second)
                continue;
            snapshot->Summons.push_back(buildUnit(controlled, BotEncounter::ActorKind::Pet));
        }
    }

    std::vector<WorldObject*> objects;
    Trinity::AllWorldObjectsInRange check(observer, 180.0f);
    Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(observer, objects, check);
    Cell::VisitAllObjects(observer, searcher, 180.0f);
    for (WorldObject* object : objects)
    {
        if (!object || object->GetMap() != observer->GetMap())
            continue;

        if (Unit* unit = object->ToUnit())
        {
            if (!seenUnits.insert(unit->GetGUID()).second)
                continue;
            Creature* creature = unit->ToCreature();
            bool const attackable = observer->IsValidAttackTarget(unit);
            if (!attackable)
            {
                if (!creature)
                    continue;
                bool const routeObserved = creature->GetEntry()
                        == snapshot->Route.InteractionEntry
                    || creature->GetEntry() == snapshot->Route.CompletionEntry;
                BotEncounter::ActorSnapshot actor = buildUnit(creature,
                    creature->IsSummon() ? BotEncounter::ActorKind::Summon
                        : BotEncounter::ActorKind::Interactable);
                actor.Attackable = false;
                actor.Interactable = creature->GetUInt32Value(UNIT_NPC_FLAGS) != 0
                    || creature->HasFlag(UNIT_NPC_FLAGS, UNIT_NPC_FLAG_SPELLCLICK);
                if (creature->IsSummon())
                    snapshot->Summons.push_back(std::move(actor));
                else if (actor.Interactable || routeObserved)
                    snapshot->Interactables.push_back(std::move(actor));
                continue;
            }
            BotEncounter::ActorKind const kind = creature
                && (creature->IsSummon() || creature->IsGuardian() || !creature->GetOwnerGUID().IsEmpty())
                ? BotEncounter::ActorKind::Summon
                : BotEncounter::ActorKind::Hostile;
            BotEncounter::ActorSnapshot actor = buildUnit(unit, kind);
            if (kind == BotEncounter::ActorKind::Summon)
                snapshot->Summons.push_back(std::move(actor));
            else
                snapshot->Hostiles.push_back(std::move(actor));
            continue;
        }

        if (GameObject* gameObject = object->ToGameObject())
        {
            BotEncounter::ActorSnapshot actor;
            actor.Guid = gameObject->GetGUID();
            actor.Entry = gameObject->GetEntry();
            actor.Kind = BotEncounter::ActorKind::Interactable;
            actor.Position = { gameObject->GetPositionX(), gameObject->GetPositionY(), gameObject->GetPositionZ() };
            actor.Facing = gameObject->GetOrientation();
            actor.Alive = gameObject->isSpawned();
            actor.Selectable = gameObject->isSpawned()
                && !gameObject->HasFlag(GAMEOBJECT_FLAGS, GO_FLAG_NOT_SELECTABLE);
            actor.Interactable = actor.Selectable;
            snapshot->Interactables.push_back(std::move(actor));
        }
    }

    auto actorOrder = [](BotEncounter::ActorSnapshot const& left, BotEncounter::ActorSnapshot const& right)
    {
        return left.Guid < right.Guid;
    };
    std::sort(snapshot->Players.begin(), snapshot->Players.end(), actorOrder);
    std::sort(snapshot->Hostiles.begin(), snapshot->Hostiles.end(), actorOrder);
    std::sort(snapshot->Summons.begin(), snapshot->Summons.end(), actorOrder);
    std::sort(snapshot->Interactables.begin(), snapshot->Interactables.end(), actorOrder);

    Cohort().EncounterSnapshot = std::move(snapshot);
    Cohort().EncounterSnapshotNextRefreshMs = nowMs + 100;
}

