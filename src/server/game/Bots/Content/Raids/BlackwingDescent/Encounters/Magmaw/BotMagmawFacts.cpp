#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawFacts.h"

#include <algorithm>

namespace BotEncounter
{
namespace
{
constexpr uint32 BossEntry = 41570;
constexpr uint32 HeadEntry = 42347;
constexpr uint32 PillarEntry = 41843;
constexpr uint32 ParasiteEntry = 41806;
constexpr uint32 ParasiteAltEntry = 42321;
constexpr uint32 RoomStalkerEntry = 47196;
constexpr uint32 PincerLeftEntry = 41620;
constexpr uint32 PincerRightEntry = 41789;
constexpr uint32 MangleNormal = 89773;
constexpr uint32 MangleAlternate = 78412;
constexpr uint32 PincerWarningAura = 87949;

bool HasAura(ActorSnapshot const& actor, uint32 spellId)
{
    return std::any_of(actor.Auras.begin(), actor.Auras.end(),
        [spellId](AuraSnapshot const& aura)
        {
            return aura.SpellId == spellId;
        });
}

bool IsMangleOwner(ActorSnapshot const& actor)
{
    return actor.Alive
        && (HasAura(actor, MangleNormal) || HasAura(actor, MangleAlternate));
}

MagmawActorFact ActorFact(ActorSnapshot const& actor)
{
    return { actor.Guid, actor.Entry, actor.Position,
        FactSource::VisibleUnitState };
}

void SortUnique(std::vector<MagmawActorFact>& actors)
{
    std::sort(actors.begin(), actors.end(),
        [](MagmawActorFact const& left, MagmawActorFact const& right)
        {
            return left.Guid.GetRawValue() < right.Guid.GetRawValue();
        });
    actors.erase(std::unique(actors.begin(), actors.end(),
        [](MagmawActorFact const& left, MagmawActorFact const& right)
        {
            return left.Guid == right.Guid;
        }), actors.end());
}

MagmawActorFact ActorFact(ActorSnapshot const& actor, FactSource source)
{
    MagmawActorFact fact = ActorFact(actor);
    fact.Source = source;
    return fact;
}

void ResolveSignal(MagmawSignal& signal)
{
    SortUnique(signal.Sources);
    signal.Active = signal.Sources.empty()
        ? MagmawTruth::False : MagmawTruth::True;
}

void InspectActor(MagmawFacts& facts, ActorSnapshot const& actor)
{
    if (actor.Entry == BossEntry)
        facts.Bosses.push_back(ActorFact(actor));
    if (actor.Entry == HeadEntry)
        facts.Heads.push_back(ActorFact(actor));
    if (actor.Alive && actor.Entry == PillarEntry)
        facts.Pillar.Sources.push_back(ActorFact(actor));
    if (actor.Alive && actor.Entry == RoomStalkerEntry
        && HasAura(actor, PincerWarningAura))
    {
        facts.Crash.Sources.push_back(ActorFact(actor,
            FactSource::VisibleAura));
        facts.PincerWarning.Sources.push_back(ActorFact(actor,
            FactSource::VisibleAura));
    }
    if (actor.Alive && (actor.Entry == PincerLeftEntry
        || actor.Entry == PincerRightEntry))
        facts.PincerVehicles.Sources.push_back(ActorFact(actor));
    if (actor.Alive && (actor.Entry == ParasiteEntry
        || actor.Entry == ParasiteAltEntry))
        facts.Parasites.Sources.push_back(ActorFact(actor));
}
}

MagmawFacts MagmawFactsReducer::Reduce(Blackboard const& board)
{
    MagmawFacts facts;
    facts.Lifecycle = board.CurrentScope;
    facts.ObservationRevision = board.Revision;
    facts.LifecycleAuthoritative = board.CurrentScope.ServerEpoch
        && !board.CurrentScope.CohortId.empty()
        && board.CurrentScope.AttemptId
        && !board.CurrentScope.NodeId.empty()
        && board.CurrentScope.MapId
        && !board.CurrentScope.EncounterId.empty();
    bool const ownsNode = board.Route.NodeId == "bwd.magmaw.encounter"
        && board.CurrentScope.NodeId == board.Route.NodeId;
    facts.OwnsNode = ownsNode ? MagmawTruth::True : MagmawTruth::False;
    facts.ProjectionAuthoritative = facts.LifecycleAuthoritative && ownsNode;
    if (!ownsNode)
        return facts;

    for (ActorSnapshot const& actor : board.Hostiles)
        InspectActor(facts, actor);
    for (ActorSnapshot const& actor : board.Summons)
        InspectActor(facts, actor);
    for (ActorSnapshot const& actor : board.Interactables)
        InspectActor(facts, actor);

    SortUnique(facts.Bosses);
    SortUnique(facts.Heads);
    facts.Crash.EvidenceSource = FactSource::VisibleAura;
    facts.PincerWarning.EvidenceSource = FactSource::VisibleAura;
    SortUnique(facts.Parasites.Sources);
    ResolveSignal(facts.Pillar);
    ResolveSignal(facts.Crash);

    std::vector<MagmawActorFact> mangleOwners;
    for (ActorSnapshot const& member : board.Players)
        if (IsMangleOwner(member))
        {
            mangleOwners.push_back(ActorFact(member));
            facts.PincerWarning.Sources.push_back(ActorFact(member,
                FactSource::VisibleAura));
        }
    SortUnique(mangleOwners);
    if (mangleOwners.size() <= 1)
    {
        facts.MangleOwnerAuthoritative = true;
        if (!mangleOwners.empty())
            facts.MangleOwnerGuid = mangleOwners.front().Guid;
    }
    ResolveSignal(facts.PincerWarning);
    ResolveSignal(facts.PincerVehicles);
    ResolveSignal(facts.Parasites);

    std::vector<MagmawActorFact> interactableBosses;
    auto collectInteractableBoss = [&interactableBosses](
        std::vector<ActorSnapshot> const& actors)
    {
        for (ActorSnapshot const& actor : actors)
            if (actor.Entry == BossEntry && actor.Alive && actor.Interactable)
                interactableBosses.push_back(ActorFact(actor));
    };
    collectInteractableBoss(board.Hostiles);
    collectInteractableBoss(board.Summons);
    collectInteractableBoss(board.Interactables);
    facts.BossInteractable = interactableBosses.empty()
        ? MagmawTruth::False : MagmawTruth::True;

    std::vector<MagmawActorFact> exposedHeads;
    auto collectExposed = [&exposedHeads](std::vector<ActorSnapshot> const& actors)
    {
        for (ActorSnapshot const& actor : actors)
            if (actor.Entry == HeadEntry && actor.Alive && actor.Selectable
                && actor.Attackable)
                exposedHeads.push_back(ActorFact(actor));
    };
    collectExposed(board.Hostiles);
    collectExposed(board.Summons);
    collectExposed(board.Interactables);
    SortUnique(exposedHeads);
    facts.HeadExposed = exposedHeads.empty()
        ? MagmawTruth::False : MagmawTruth::True;
    if (exposedHeads.size() == 1)
    {
        facts.ExposedHeadGuid = exposedHeads.front().Guid;
        facts.ExposedHeadIdentityAuthoritative = true;
    }

    if (board.NativeWipeState == "wiped")
        facts.WipeLocked = MagmawTruth::True;
    else if (board.NativeWipeState == "ready"
        || board.NativeWipeState == "engaged"
        || board.NativeWipeState == "partial_deaths")
        facts.WipeLocked = MagmawTruth::False;

    if (board.NativeEncounterPhase == "combat")
        facts.Phase = MagmawPhase::Combat;
    else if (board.NativeEncounterPhase == "recovery")
        facts.Phase = MagmawPhase::Recovery;
    else if (board.NativeEncounterPhase == "completed")
        facts.Phase = MagmawPhase::Completed;
    else if (board.NativeEncounterPhase == "formation")
        facts.Phase = MagmawPhase::Prepull;
    if (facts.Phase != MagmawPhase::Unknown)
        facts.PhaseAuthoritative = true;

    if (facts.Bosses.size() == 1)
    {
        ActorSnapshot const* boss = board.FindActor(facts.Bosses.front().Guid);
        if (boss)
        {
            bool const engaged = boss->InCombat || !boss->VictimGuid.IsEmpty()
                || board.NativeBossState == "in_progress";
            if (engaged)
                facts.Prepull = MagmawTruth::False;
            else if (board.NativeBossState == "not_in_progress")
                facts.Prepull = MagmawTruth::True;
        }
    }
    return facts;
}

bool MagmawFactsCache::Matches(Scope const& scope, uint64 revision) const
{
    return _facts.Lifecycle == scope
        && _facts.ObservationRevision == revision;
}

std::shared_ptr<MagmawFactsCache const> MagmawFactsCache::ForSnapshot(
    std::shared_ptr<MagmawFactsCache const> const& current,
    Blackboard const& snapshot)
{
    if (current && current->Matches(snapshot.CurrentScope, snapshot.Revision))
        return current;

    MagmawFacts facts = MagmawFactsReducer::Reduce(snapshot);
    EdgeCounters counters;
    MagmawFacts const* previous = nullptr;
    if (current && current->_facts.Lifecycle == snapshot.CurrentScope)
    {
        counters = current->_counters;
        previous = &current->_facts;
    }
    auto observeEdge = [previous](MagmawSignal& signal,
        MagmawSignal MagmawFacts::* member, uint64& counter)
    {
        if (signal.Active != MagmawTruth::True || !previous)
            return;
        MagmawSignal const& before = previous->*member;
        if (before.Active == MagmawTruth::False)
            signal.Generation = { MagmawGenerationKind::ObservationEdge,
                ++counter, signal.EvidenceSource };
        else if (before.Active == MagmawTruth::True)
            signal.Generation = before.Generation;
    };
    observeEdge(facts.Pillar, &MagmawFacts::Pillar, counters.Pillar);
    observeEdge(facts.Crash, &MagmawFacts::Crash, counters.Crash);
    observeEdge(facts.PincerWarning, &MagmawFacts::PincerWarning,
        counters.PincerWarning);
    observeEdge(facts.PincerVehicles, &MagmawFacts::PincerVehicles,
        counters.PincerVehicles);
    observeEdge(facts.Parasites, &MagmawFacts::Parasites,
        counters.Parasites);
    return std::shared_ptr<MagmawFactsCache const>(
        new MagmawFactsCache(std::move(facts), counters));
}
}
