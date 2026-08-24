#include "DetourNavMesh.h"
#include "DetourNavMeshQuery.h"
#include "DetourAlloc.h"
#include "DetourCommon.h"
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>

struct TileHeader { uint32_t magic, dtVersion, mmapVersion, size; char usesLiquids; char padding[3]; };
static_assert(sizeof(TileHeader) == 20);
struct TestPoint { char const* label; float x, y, z, dx, dy, dz; };
constexpr int MaxPath = 74;
constexpr float Step = 4.0f;
constexpr float Slop = 0.3f;

static bool InRangeYZX(float const* a, float const* b, float radius, float height)
{
    float dx = b[0] - a[0], dy = b[1] - a[1], dz = b[2] - a[2];
    return dx*dx + dz*dz < radius*radius && std::fabs(dy) < height;
}

static unsigned FixupCorridor(dtPolyRef* path, unsigned pathSize, unsigned maxPath,
    dtPolyRef const* visited, unsigned visitedSize)
{
    int furthestPath = -1, furthestVisited = -1;
    for (int i = int(pathSize) - 1; i >= 0; --i)
    {
        bool found = false;
        for (int j = int(visitedSize) - 1; j >= 0; --j)
            if (path[i] == visited[j])
            {
                furthestPath = i;
                furthestVisited = j;
                found = true;
            }
        if (found)
            break;
    }
    if (furthestPath == -1 || furthestVisited == -1)
        return pathSize;
    unsigned required = visitedSize - furthestVisited;
    unsigned original = unsigned(furthestPath + 1) < pathSize ? furthestPath + 1 : pathSize;
    unsigned size = pathSize > original ? pathSize - original : 0;
    if (required + size > maxPath)
        size = maxPath - required;
    if (size)
        std::memmove(path + required, path + original, size * sizeof(dtPolyRef));
    for (unsigned i = 0; i < required; ++i)
        path[i] = visited[(visitedSize - 1) - i];
    return required + size;
}

static bool GetSteerTarget(dtNavMeshQuery* query, float const* start, float const* end,
    dtPolyRef const* path, unsigned pathSize, float* steer, unsigned char& steerFlag, dtPolyRef& steerRef)
{
    float points[9]; unsigned char flags[3]; dtPolyRef refs[3]; int count = 0;
    dtStatus status = query->findStraightPath(start, end, path, pathSize, points, flags, refs, &count, 3);
    if (!count || dtStatusFailed(status))
        return false;
    int index = 0;
    while (index < count)
    {
        if ((flags[index] & DT_STRAIGHTPATH_OFFMESH_CONNECTION) || !InRangeYZX(&points[index*3], start, Slop, 1000.0f))
            break;
        ++index;
    }
    if (index >= count)
        return false;
    dtVcopy(steer, &points[index*3]);
    steer[1] = start[1];
    steerFlag = flags[index];
    steerRef = refs[index];
    return true;
}

static dtStatus FindSmoothPath(dtNavMesh* mesh, dtNavMeshQuery* query, dtQueryFilter const& filter,
    float const* start, float const* end, dtPolyRef const* corridor, unsigned corridorSize,
    float* smooth, int* smoothSize)
{
    *smoothSize = 0;
    unsigned count = 0;
    dtPolyRef polys[MaxPath];
    std::memcpy(polys, corridor, corridorSize * sizeof(dtPolyRef));
    unsigned polyCount = corridorSize;
    float iter[3], target[3];
    if (corridorSize > 1)
    {
        if (dtStatusFailed(query->closestPointOnPolyBoundary(polys[0], start, iter)) ||
            dtStatusFailed(query->closestPointOnPolyBoundary(polys[polyCount - 1], end, target)))
            return DT_FAILURE;
    }
    else
    {
        dtVcopy(iter, start);
        dtVcopy(target, end);
    }
    dtVcopy(&smooth[count++ * 3], iter);
    while (polyCount && count < MaxPath)
    {
        float steer[3]; unsigned char steerFlag = 0; dtPolyRef steerRef = 0;
        if (!GetSteerTarget(query, iter, target, polys, polyCount, steer, steerFlag, steerRef))
            break;
        bool endOfPath = (steerFlag & DT_STRAIGHTPATH_END) != 0;
        bool offMesh = (steerFlag & DT_STRAIGHTPATH_OFFMESH_CONNECTION) != 0;
        float delta[3]; dtVsub(delta, steer, iter);
        float length = std::sqrt(dtVdot(delta, delta));
        if ((endOfPath || offMesh) && length < Step)
            length = 1.0f;
        else
            length = Step / length;
        float moveTarget[3], result[3];
        dtVmad(moveTarget, iter, delta, length);
        dtPolyRef visited[16]; int visitedCount = 0;
        if (dtStatusFailed(query->moveAlongSurface(polys[0], iter, moveTarget, &filter, result, visited, &visitedCount, 16)))
            return DT_FAILURE;
        polyCount = FixupCorridor(polys, polyCount, MaxPath, visited, visitedCount);
        query->getPolyHeight(polys[0], result, &result[1]);
        result[1] += 0.5f;
        dtVcopy(iter, result);
        if (endOfPath && InRangeYZX(iter, steer, Slop, 1.0f))
        {
            dtVcopy(iter, target);
            if (count < MaxPath)
                dtVcopy(&smooth[count++ * 3], iter);
            break;
        }
        if (count < MaxPath)
            dtVcopy(&smooth[count++ * 3], iter);
    }
    *smoothSize = count;
    return count < MaxPath ? DT_SUCCESS : DT_FAILURE;
}

static float Distance3(float const* a, float const* b)
{
    float x = a[0] - b[0], y = a[1] - b[1], z = a[2] - b[2];
    return std::sqrt(x*x + y*y + z*z);
}

int main()
{
    std::ifstream mapFile("data/mmaps/669.mmap", std::ios::binary);
    dtNavMeshParams params{};
    mapFile.read(reinterpret_cast<char*>(&params), sizeof(params));
    std::cout << "params_read=" << mapFile.gcount() << " origin=" << params.orig[0] << ',' << params.orig[1] << ',' << params.orig[2]
              << " tile=" << params.tileWidth << ',' << params.tileHeight << " maxTiles=" << params.maxTiles << " maxPolys=" << params.maxPolys << '\n';

    dtNavMesh* mesh = dtAllocNavMesh();
    std::cout << "mesh_init=0x" << std::hex << mesh->init(&params) << std::dec << '\n';
    int loaded = 0;
    for (auto const& entry : std::filesystem::directory_iterator("data/mmaps"))
    {
        std::string name = entry.path().filename().string();
        if (name.size() != 14 || name.rfind("669", 0) != 0 || name.substr(name.size() - 7) != ".mmtile")
            continue;
        std::ifstream tileFile(entry.path(), std::ios::binary);
        TileHeader header{};
        tileFile.read(reinterpret_cast<char*>(&header), sizeof(header));
        unsigned char* data = static_cast<unsigned char*>(dtAlloc(header.size, DT_ALLOC_PERM));
        tileFile.read(reinterpret_cast<char*>(data), header.size);
        auto* meshHeader = reinterpret_cast<dtMeshHeader*>(data);
        dtTileRef ref = 0;
        dtStatus status = mesh->addTile(data, header.size, DT_TILE_FREE_DATA, 0, &ref);
        std::cout << "tile=" << name << " version=" << header.mmapVersion << " size=" << header.size
                  << " meshxy=" << meshHeader->x << ',' << meshHeader->y << " add=0x" << std::hex << status << std::dec << " ref=" << ref << '\n';
        if (dtStatusSucceed(status))
            ++loaded;
        else
            dtFree(data);
    }
    std::cout << "loaded=" << loaded << '\n';

    dtNavMeshQuery* query = dtAllocNavMeshQuery();
    std::cout << "query_init=0x" << std::hex << query->init(mesh, 1024) << std::dec << '\n';
    dtQueryFilter filter;
    filter.setIncludeFlags(0x1 | 0x4 | 0x8);
    filter.setExcludeFlags(0);
    TestPoint tests[] = {
        {"30003", -288.800f, -86.483f, 214.150f, -295.0f, -71.5f, 213.25f},
        {"30008", -338.018f, -64.932f, 212.751f, -325.0f, -64.0f, 212.82f},
        {"30003_reposition", -295.0f, -71.5f, 213.25f,
            -296.0f, -69.9f, 213.485f},
        {"30004_reposition", -299.0f, -75.0f, 213.65f,
            -298.8f, -71.5f, 213.461f},
        {"30005_reposition", -343.508f, -44.4466f, 211.947f,
            -311.5f, -71.3f, 213.292f},
        {"30007_reposition", -295.0f, -82.0f, 213.8f,
            -292.5f, -69.1f, 214.024f},
        {"minimum_distance_exit_retained", -288.8f, -72.289f, 213.473f,
            -285.742f, -73.2144f, 213.473f},
        {"tank1_pull_away", -289.289093f, -57.7575f, 212.932236f,
            -288.8f, -43.0f, 212.301f},
        {"tank2_pull_away", -322.858002f, -48.286201f, 211.999359f,
            -321.5f, -30.0f, 211.283429f},
        {"chainwielder_patrol_pull", -346.5827f, -83.71657f, 213.9893f,
            -345.872f, -110.0f, 213.964f}
    };
    for (TestPoint const& test : tests)
    {
        float start[3] = {test.y, test.z, test.x};
        float end[3] = {test.dy, test.dz, test.dx};
        float startClosest[3]{}, endClosest[3]{};
        float extents[3] = {3.0f, 5.0f, 3.0f};
        dtPolyRef startRef = 0, endRef = 0;
        dtStatus startStatus = query->findNearestPoly(start, extents, &filter, &startRef, startClosest);
        if (!startRef)
        {
            extents[1] = 50.0f;
            startStatus = query->findNearestPoly(start, extents, &filter, &startRef, startClosest);
        }
        extents[1] = 5.0f;
        dtStatus endStatus = query->findNearestPoly(end, extents, &filter, &endRef, endClosest);
        if (!endRef)
        {
            extents[1] = 50.0f;
            endStatus = query->findNearestPoly(end, extents, &filter, &endRef, endClosest);
        }
        std::cout << '\n' << test.label << " start_status=0x" << std::hex << startStatus << " ref=" << startRef << std::dec
                  << " nearest=" << startClosest[2] << ',' << startClosest[0] << ',' << startClosest[1] << " distance=" << Distance3(start, startClosest) << '\n';
        std::cout << test.label << " end_status=0x" << std::hex << endStatus << " ref=" << endRef << std::dec
                  << " nearest=" << endClosest[2] << ',' << endClosest[0] << ',' << endClosest[1] << " distance=" << Distance3(end, endClosest) << '\n';
        std::cout << test.label << " nearest_terminal=" << endClosest[2] << ','
                  << endClosest[0] << ',' << endClosest[1]
                  << " requested_endz=" << std::fabs(endClosest[1] - test.dz) << '\n';

        dtPolyRef corridor[74]{};
        int corridorSize = 0;
        dtStatus pathStatus = query->findPath(startRef, endRef, start, end, &filter, corridor, &corridorSize, 74);
        std::cout << test.label << " findPath=0x" << std::hex << pathStatus << std::dec << " polys=" << corridorSize
                  << " complete=" << (corridorSize && corridor[corridorSize - 1] == endRef) << '\n';

        float straight[74 * 3]{};
        unsigned char flags[74]{};
        dtPolyRef refs[74]{};
        int straightSize = 0;
        dtStatus straightStatus = query->findStraightPath(start, end, corridor, corridorSize, straight, flags, refs, &straightSize, 74);
        std::cout << test.label << " straight=0x" << std::hex << straightStatus << std::dec << " points=" << straightSize;
        if (straightSize)
        {
            float const* terminal = &straight[(straightSize - 1) * 3];
            std::cout << " terminal=" << terminal[2] << ',' << terminal[0] << ',' << terminal[1]
                      << " end2d=" << std::hypot(terminal[2] - test.dx, terminal[0] - test.dy)
                      << " endz=" << std::fabs(terminal[1] - test.dz);
            if (std::string(test.label) == "minimum_distance_exit_retained")
                std::cout << '\n' << test.label << " actual_endpoint="
                          << terminal[2] << ',' << terminal[0] << ',' << terminal[1]
                          << " requested_end2d_miss="
                          << std::hypot(terminal[2] - test.dx, terminal[0] - test.dy);
        }
        std::cout << '\n';
        for (int i = 0; i < straightSize; ++i)
            std::cout << " point" << i << '=' << straight[i*3+2] << ',' << straight[i*3] << ',' << straight[i*3+1]
                      << " flag=" << unsigned(flags[i]) << " ref=" << refs[i] << '\n';
        float smooth[MaxPath * 3]{};
        int smoothSize = 0;
        dtStatus smoothStatus = FindSmoothPath(mesh, query, filter, start, end, corridor, corridorSize, smooth, &smoothSize);
        std::cout << test.label << " smooth=0x" << std::hex << smoothStatus << std::dec << " points=" << smoothSize;
        if (smoothSize)
        {
            float const* terminal = &smooth[(smoothSize - 1) * 3];
            std::cout << " terminal=" << terminal[2] << ',' << terminal[0] << ',' << terminal[1]
                      << " end2d=" << std::hypot(terminal[2] - test.dx, terminal[0] - test.dy)
                      << " endz=" << std::fabs(terminal[1] - test.dz);
        }
        std::cout << '\n';
        if (std::string(test.label) == "chainwielder_patrol_pull")
        {
            float minimumSource0 = 10000.0f;
            float minimumSource1 = 10000.0f;
            for (int i = 0; i < smoothSize; ++i)
            {
                float const x = smooth[i * 3 + 2];
                float const y = smooth[i * 3];
                minimumSource0 = std::min(minimumSource0,
                    std::hypot(x - -298.833f, y - -50.349f));
                minimumSource1 = std::min(minimumSource1,
                    std::hypot(x - -307.913f, y - -49.5694f));
            }
            std::cout << test.label << " future_guard_minimums="
                      << minimumSource0 << ',' << minimumSource1 << '\n';
        }
    }
    dtFreeNavMeshQuery(query);
    dtFreeNavMesh(mesh);
}
