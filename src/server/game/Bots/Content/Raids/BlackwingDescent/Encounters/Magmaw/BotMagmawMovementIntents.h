#ifndef TRINITY_BOT_MAGMAW_MOVEMENT_INTENTS_H
#define TRINITY_BOT_MAGMAW_MOVEMENT_INTENTS_H

#include "Bots/Decision/BotIntentSink.h"

#include <cstddef>
#include <utility>
#include <vector>

namespace BotEncounter
{
enum class MagmawMovementProposalOrigin : uint8
{
    PrepullFormation,
    Hazard,
    HookPreposition,
    HookApproach,
    FormationRestore,
    TransferLaneTask
};

enum class MagmawMovementKernelAdmission : uint8
{
    Admitted,
    MechanicUnmapped,
    SurvivalPreempted,
    TransferBindingRejected
};

inline MagmawMovementKernelAdmission EvaluateMagmawMovementKernelAdmission(
    bool mechanicMapped, bool transferBindingRequired,
    bool safetyMovementPending, BotActionArbitration::Priority priority)
{
    if (!mechanicMapped)
        return MagmawMovementKernelAdmission::MechanicUnmapped;
    if (transferBindingRequired)
        return MagmawMovementKernelAdmission::TransferBindingRejected;
    if (safetyMovementPending
        && priority != BotActionArbitration::Priority::Survival)
        return MagmawMovementKernelAdmission::SurvivalPreempted;
    return MagmawMovementKernelAdmission::Admitted;
}

inline char const* RejectionReason(MagmawMovementKernelAdmission admission)
{
    switch (admission)
    {
        case MagmawMovementKernelAdmission::MechanicUnmapped:
            return "magmaw_movement_mechanic_unmapped";
        case MagmawMovementKernelAdmission::SurvivalPreempted:
            return "magmaw_survival_movement_pending";
        case MagmawMovementKernelAdmission::TransferBindingRejected:
            return "magmaw_transfer_binding_rejected";
        case MagmawMovementKernelAdmission::Admitted:
            return "";
    }
    return "magmaw_movement_admission_unknown";
}

inline char const* ToString(MagmawMovementProposalOrigin origin)
{
    switch (origin)
    {
        case MagmawMovementProposalOrigin::PrepullFormation:
            return "adaptive_magmaw.prepull_formation";
        case MagmawMovementProposalOrigin::Hazard:
            return "adaptive_magmaw.hazard";
        case MagmawMovementProposalOrigin::HookPreposition:
            return "adaptive_magmaw.hook_preposition";
        case MagmawMovementProposalOrigin::HookApproach:
            return "adaptive_magmaw.hook_approach";
        case MagmawMovementProposalOrigin::FormationRestore:
            return "adaptive_magmaw.formation_restore";
        case MagmawMovementProposalOrigin::TransferLaneTask:
            return "adaptive_magmaw.transfer_lane_task";
    }
    return "adaptive_magmaw.unknown";
}

// Passive, encounter-typed view over the shared intent sink. Origins remain
// paired by index with the sink proposals and are diagnostic metadata only.
// Selection remains exclusively in BotActionArbitration::Kernel.
class MagmawMovementIntentCollection
{
public:
    void Propose(MagmawMovementProposalOrigin origin,
        BotNativeAction::Candidate candidate)
    {
        _origins.push_back(origin);
        _sink.Propose(std::move(candidate));
    }

    std::vector<BotNativeAction::Candidate> const& Proposals() const
    {
        return _sink.Proposals();
    }

    MagmawMovementProposalOrigin Origin(size_t index) const
    {
        return _origins.at(index);
    }

    size_t Size() const { return _origins.size(); }
    bool Empty() const { return _origins.empty(); }

    // Transitional read-only view for retained strategy fixtures. Runtime
    // preparation never consumes this view; it submits Proposals() in full.
    bool has_value() const { return !Empty(); }
    explicit operator bool() const { return !Empty(); }
    BotNativeAction::Candidate const* operator->() const
    {
        return Empty() ? nullptr : &Proposals().front();
    }
    BotNativeAction::Candidate const& operator*() const
    {
        return Proposals().front();
    }

    bool Replace(size_t index, MagmawMovementProposalOrigin origin,
        BotNativeAction::Candidate candidate)
    {
        if (index >= _origins.size())
            return false;
        BotDecision::BotIntentSink rebuilt;
        for (size_t proposalIndex = 0; proposalIndex < Size(); ++proposalIndex)
            rebuilt.Propose(proposalIndex == index
                ? candidate : Proposals()[proposalIndex]);
        _sink = std::move(rebuilt);
        _origins[index] = origin;
        return true;
    }

private:
    BotDecision::BotIntentSink _sink;
    std::vector<MagmawMovementProposalOrigin> _origins;
};
}

#endif
