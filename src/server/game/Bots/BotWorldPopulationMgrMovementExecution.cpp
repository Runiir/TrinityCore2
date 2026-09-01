#include "Bots/BotWorldPopulationMgrMovement.h"

#include "Bots/BotWorldPopulationMgrNativeFloor.h"

namespace BotWorldMovement
{
ExecutionObservation BeginExecutionObservation(float requestedX,
    float requestedY, float requestedZ, std::uint64_t receiptId)
{
    ExecutionObservation execution = BeginUnavailableExecutionObservation(
        requestedX, requestedY, requestedZ);
    execution.Available = true;
    execution.Disposition = ExecutionDisposition::Rejected;
    execution.ReceiptId = receiptId;
    return execution;
}

ExecutionObservation BeginUnavailableExecutionObservation(float requestedX,
    float requestedY, float requestedZ)
{
    ExecutionObservation execution;
    execution.RequestedX = requestedX;
    execution.RequestedY = requestedY;
    execution.RequestedZ = requestedZ;
    return execution;
}

void ObserveExecutionProof(ExecutionObservation& execution,
    NativePathProofObservation const& proof)
{
    execution.EndpointResult = proof.EndpointResult;
    execution.CorridorReachedEndPoly = proof.CorridorReachedEndPoly;
    execution.ResolvedEndpointAvailable = proof.ResolvedEndpointAvailable;
    execution.ResolvedEndpointX = proof.ResolvedEndpointX;
    execution.ResolvedEndpointY = proof.ResolvedEndpointY;
    execution.ResolvedEndpointZ = proof.ResolvedEndpointZ;
    execution.ActualEndpointMatchedResolved =
        proof.ActualEndpointMatchedResolved;
    execution.RequestedEndpointMatched = proof.EndpointMatched;
}
}
