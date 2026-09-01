/*
 * This file is part of the TrinityCore Project. See AUTHORS file for Copyright information
 *
 * This program is free software; you can redistribute it and/or modify it
 * under the terms of the GNU General Public License as published by the
 * Free Software Foundation; either version 2 of the License, or (at your
 * option) any later version.
 */

#include "PathGenerator.h"

#include "Creature.h"
#include "DetourCommon.h"
#include "Log.h"

#include <cmath>
#include <cstring>

void PathGenerator::ResetEndpointObservation()
{
    _endpointResult = PathEndpointResult::Unavailable;
    _corridorReachedEndPoly = false;
    _resolvedEndPositionAvailable = false;
    _resolvedEndPositionProjected = false;
    _resolvedEndPosition = G3D::Vector3::zero();
}

void PathGenerator::SetResolvedEndPosition(float const* point, bool projected)
{
    _resolvedEndPosition = G3D::Vector3(point[2], point[0], point[1]);
    _resolvedEndPositionAvailable = true;
    _resolvedEndPositionProjected = projected;
}

void PathGenerator::MarkResolvedEndPositionReached()
{
    _endpointResult = _resolvedEndPositionProjected
        ? PathEndpointResult::ReachedProjectedEndPoly
        : PathEndpointResult::ReachedRequested;
}

uint32 PathGenerator::FixupCorridor(dtPolyRef* path, uint32 npath,
    uint32 maxPath, dtPolyRef const* visited, uint32 nvisited)
{
    int32 furthestPath = -1;
    int32 furthestVisited = -1;

    for (int32 i = npath - 1; i >= 0; --i)
    {
        bool found = false;
        for (int32 j = nvisited - 1; j >= 0; --j)
        {
            if (path[i] == visited[j])
            {
                furthestPath = i;
                furthestVisited = j;
                found = true;
            }
        }
        if (found)
            break;
    }

    if (furthestPath == -1 || furthestVisited == -1)
        return npath;

    uint32 req = nvisited - furthestVisited;
    uint32 orig = uint32(furthestPath + 1) < npath
        ? furthestPath + 1 : npath;
    uint32 size = npath > orig ? npath - orig : 0;
    if (req + size > maxPath)
        size = maxPath - req;

    if (size)
        memmove(path + req, path + orig, size * sizeof(dtPolyRef));

    for (uint32 i = 0; i < req; ++i)
        path[i] = visited[(nvisited - 1) - i];

    return req + size;
}

bool PathGenerator::GetSteerTarget(float const* startPos,
    float const* endPos, float minTargetDist, dtPolyRef const* path,
    uint32 pathSize, float* steerPos, unsigned char& steerPosFlag,
    dtPolyRef& steerPosRef)
{
    static uint32 constexpr MaxSteerPoints = 3;
    float steerPath[MaxSteerPoints * VERTEX_SIZE];
    unsigned char steerPathFlags[MaxSteerPoints];
    dtPolyRef steerPathPolys[MaxSteerPoints];
    uint32 nsteerPath = 0;
    dtStatus dtResult = _navMeshQuery->findStraightPath(startPos, endPos,
        path, pathSize, steerPath, steerPathFlags, steerPathPolys,
        reinterpret_cast<int*>(&nsteerPath), MaxSteerPoints);
    if (!nsteerPath || dtStatusFailed(dtResult))
        return false;

    uint32 ns = 0;
    while (ns < nsteerPath)
    {
        if ((steerPathFlags[ns] & DT_STRAIGHTPATH_OFFMESH_CONNECTION)
            || !InRangeYZX(&steerPath[ns * VERTEX_SIZE], startPos,
                minTargetDist, 1000.0f))
            break;
        ++ns;
    }
    if (ns >= nsteerPath)
        return false;

    dtVcopy(steerPos, &steerPath[ns * VERTEX_SIZE]);
    steerPos[1] = startPos[1];
    steerPosFlag = steerPathFlags[ns];
    steerPosRef = steerPathPolys[ns];
    return true;
}

dtStatus PathGenerator::FindSmoothPath(float const* startPos,
    float const* endPos, dtPolyRef const* polyPath, uint32 polyPathSize,
    float* smoothPath, int* smoothPathSize, uint32 maxSmoothPathSize)
{
    *smoothPathSize = 0;
    uint32 nsmoothPath = 0;

    dtPolyRef polys[MAX_PATH_LENGTH];
    memcpy(polys, polyPath, sizeof(dtPolyRef) * polyPathSize);
    uint32 npolys = polyPathSize;
    float iterPos[VERTEX_SIZE];
    float targetPos[VERTEX_SIZE];

    if (polyPathSize > 1)
    {
        if (dtStatusFailed(_navMeshQuery->closestPointOnPolyBoundary(
                polys[0], startPos, iterPos))
            || dtStatusFailed(_navMeshQuery->closestPointOnPolyBoundary(
                polys[npolys - 1], endPos, targetPos)))
        {
            _endpointResult = PathEndpointResult::Failure;
            return DT_FAILURE;
        }
    }
    else
    {
        dtVcopy(iterPos, startPos);
        dtVcopy(targetPos, endPos);
    }

    bool const projected = targetPos[0] != endPos[0]
        || targetPos[1] != endPos[1] || targetPos[2] != endPos[2];
    SetResolvedEndPosition(targetPos, projected);

    dtVcopy(&smoothPath[nsmoothPath * VERTEX_SIZE], iterPos);
    ++nsmoothPath;

    while (npolys && nsmoothPath < maxSmoothPathSize)
    {
        float steerPos[VERTEX_SIZE];
        unsigned char steerPosFlag;
        dtPolyRef steerPosRef = INVALID_POLYREF;
        if (!GetSteerTarget(iterPos, targetPos, SMOOTH_PATH_SLOP, polys,
                npolys, steerPos, steerPosFlag, steerPosRef))
        {
            _endpointResult = PathEndpointResult::NoSteer;
            break;
        }

        bool const endOfPath =
            (steerPosFlag & DT_STRAIGHTPATH_END) != 0;
        bool const offMeshConnection =
            (steerPosFlag & DT_STRAIGHTPATH_OFFMESH_CONNECTION) != 0;
        float delta[VERTEX_SIZE];
        dtVsub(delta, steerPos, iterPos);
        float len = dtMathSqrtf(dtVdot(delta, delta));
        if ((endOfPath || offMeshConnection)
            && len < SMOOTH_PATH_STEP_SIZE)
            len = 1.0f;
        else
            len = SMOOTH_PATH_STEP_SIZE / len;

        float moveTarget[VERTEX_SIZE];
        dtVmad(moveTarget, iterPos, delta, len);
        float result[VERTEX_SIZE];
        static uint32 constexpr MaxVisitedPolys = 16;
        dtPolyRef visited[MaxVisitedPolys];
        uint32 nvisited = 0;
        if (dtStatusFailed(_navMeshQuery->moveAlongSurface(polys[0], iterPos,
                moveTarget, &_filter, result, visited,
                reinterpret_cast<int*>(&nvisited), MaxVisitedPolys)))
        {
            _endpointResult = PathEndpointResult::Failure;
            return DT_FAILURE;
        }
        npolys = FixupCorridor(polys, npolys, MAX_PATH_LENGTH, visited,
            nvisited);
        if (!npolys)
        {
            _endpointResult = PathEndpointResult::CorridorExhausted;
            break;
        }

        if (dtStatusFailed(_navMeshQuery->getPolyHeight(
                polys[0], result, &result[1])))
            TC_LOG_DEBUG("maps.mmaps", "Cannot find height at position X: %f Y: %f Z: %f for unit %u",
                result[2], result[0], result[1], _source->GetEntry());
        result[1] += 0.5f;
        dtVcopy(iterPos, result);

        if (endOfPath
            && InRangeYZX(iterPos, steerPos, SMOOTH_PATH_SLOP, 1.0f))
        {
            dtVcopy(iterPos, targetPos);
            if (nsmoothPath < maxSmoothPathSize)
            {
                dtVcopy(&smoothPath[nsmoothPath * VERTEX_SIZE], iterPos);
                ++nsmoothPath;
            }
            MarkResolvedEndPositionReached();
            break;
        }
        if (offMeshConnection
            && InRangeYZX(iterPos, steerPos, SMOOTH_PATH_SLOP, 1.0f))
        {
            dtPolyRef prevRef = INVALID_POLYREF;
            dtPolyRef polyRef = polys[0];
            uint32 npos = 0;
            while (npos < npolys && polyRef != steerPosRef)
            {
                prevRef = polyRef;
                polyRef = polys[npos];
                ++npos;
            }
            for (uint32 i = npos; i < npolys; ++i)
                polys[i - npos] = polys[i];
            npolys -= npos;
            if (!npolys)
            {
                _endpointResult = PathEndpointResult::CorridorExhausted;
                break;
            }

            float connectionStartPos[VERTEX_SIZE];
            float connectionEndPos[VERTEX_SIZE];
            if (dtStatusSucceed(_navMesh->getOffMeshConnectionPolyEndPoints(
                    prevRef, polyRef, connectionStartPos, connectionEndPos)))
            {
                if (nsmoothPath < maxSmoothPathSize)
                {
                    dtVcopy(&smoothPath[nsmoothPath * VERTEX_SIZE],
                        connectionStartPos);
                    ++nsmoothPath;
                }
                dtVcopy(iterPos, connectionEndPos);
                if (dtStatusFailed(_navMeshQuery->getPolyHeight(
                        polys[0], iterPos, &iterPos[1])))
                {
                    _endpointResult = PathEndpointResult::Failure;
                    return DT_FAILURE;
                }
                iterPos[1] += 0.5f;
            }
        }

        if (nsmoothPath < maxSmoothPathSize)
        {
            dtVcopy(&smoothPath[nsmoothPath * VERTEX_SIZE], iterPos);
            ++nsmoothPath;
        }
    }

    if (_endpointResult == PathEndpointResult::Unavailable)
        _endpointResult = nsmoothPath >= maxSmoothPathSize
            ? PathEndpointResult::Capacity
            : PathEndpointResult::CorridorExhausted;
    *smoothPathSize = nsmoothPath;
    return nsmoothPath < MAX_POINT_PATH_LENGTH ? DT_SUCCESS : DT_FAILURE;
}

bool PathGenerator::InRangeYZX(float const* v1, float const* v2, float r,
    float h) const
{
    float const dx = v2[0] - v1[0];
    float const dy = v2[1] - v1[1];
    float const dz = v2[2] - v1[2];
    return (dx * dx + dz * dz) < r * r && std::fabs(dy) < h;
}
