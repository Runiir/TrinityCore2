// Read public static collision navigation tiles; no server or character DB.
#include "DetourAlloc.h"
#include "DetourNavMesh.h"
#include "DetourNavMeshQuery.h"
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

struct TileHeader { uint32_t magic, detourVersion, version, size; uint8_t liquids, padding[3]; };
static_assert(sizeof(TileHeader) == 20);

int main(int argc, char** argv)
{
    try
    {
        if (argc != 9) throw std::runtime_error("expected data directory, map, start XYZ, goal XYZ");
        std::filesystem::path directory(argv[1]);
        int map = std::stoi(argv[2]);
        float start[3] = {std::stof(argv[4]), std::stof(argv[5]), std::stof(argv[3])};
        float goal[3] = {std::stof(argv[7]), std::stof(argv[8]), std::stof(argv[6])};
        for (float value : start) if (!std::isfinite(value)) throw std::runtime_error("invalid start");
        for (float value : goal) if (!std::isfinite(value)) throw std::runtime_error("invalid goal");
        if (std::hypot(start[0]-goal[0], start[2]-goal[2]) > 600)
            throw std::runtime_error("local route exceeds 600 yards");
        char prefix[16]; std::snprintf(prefix, sizeof(prefix), "%03d", map);
        dtNavMeshParams params;
        std::ifstream settings(directory/(std::string(prefix)+".mmap"), std::ios::binary);
        if (!settings.read(reinterpret_cast<char*>(&params), sizeof(params))) throw std::runtime_error("map parameters unavailable");
        dtNavMesh mesh;
        if (dtStatusFailed(mesh.init(&params))) throw std::runtime_error("map initialization failed");
        int loaded = 0;
        for (auto const& file : std::filesystem::directory_iterator(directory))
        {
            std::string name = file.path().filename().string();
            if (!name.starts_with(prefix) || file.path().extension() != ".mmtile") continue;
            std::ifstream input(file.path(), std::ios::binary); TileHeader header; dtMeshHeader tile;
            if (!input.read(reinterpret_cast<char*>(&header),sizeof(header)) || header.magic != 0x4d4d4150
                || header.version != 14 || header.detourVersion != DT_NAVMESH_VERSION
                || header.size < sizeof(tile) || header.size > 16*1024*1024) throw std::runtime_error("unsupported tile header");
            if (!input.read(reinterpret_cast<char*>(&tile),sizeof(tile))) throw std::runtime_error("truncated tile");
            bool nearby = true;
            for (int axis : {0,2})
                if (tile.bmax[axis] < std::min(start[axis],goal[axis])-100
                    || tile.bmin[axis] > std::max(start[axis],goal[axis])+100) nearby = false;
            if (!nearby) continue;
            input.seekg(sizeof(header));
            auto data = static_cast<unsigned char*>(dtAlloc(header.size,DT_ALLOC_PERM));
            if (!data || !input.read(reinterpret_cast<char*>(data),header.size)) throw std::runtime_error("truncated navigation data");
            if (dtStatusFailed(mesh.addTile(data,header.size,DT_TILE_FREE_DATA,0,nullptr)))
            { dtFree(data); throw std::runtime_error("tile initialization failed"); }
            ++loaded;
        }
        dtNavMeshQuery query;
        if (dtStatusFailed(query.init(&mesh,8192))) throw std::runtime_error("query initialization failed");
        dtQueryFilter filter; filter.setIncludeFlags(1); filter.setExcludeFlags(0); // NAV_GROUND only
        float startExtents[3] = {4,8,4}, goalExtents[3] = {4,40,4};
        dtPolyRef first = 0, last = 0; float begin[3], end[3];
        query.findNearestPoly(start,startExtents,&filter,&first,begin);
        if (!first) throw std::runtime_error("no walkable ground near player feet");
        // Telescope packets provide heading, not the unknown target's height.
        // Consider ground at every elevation in the local column, preferring
        // horizontal proximity and requiring a fully connected walking path.
        dtPolyRef candidates[256], corridor[1024]; int candidatesCount = 0, count = 0;
        auto status = query.queryPolygons(goal,goalExtents,&filter,candidates,&candidatesCount,256);
        if (dtStatusFailed(status) || (status & DT_BUFFER_TOO_SMALL)) throw std::runtime_error("ground column exceeds query budget");
        float best = INFINITY;
        for (int i = 0; i < candidatesCount; ++i)
        {
            float point[3];
            if (dtStatusFailed(query.closestPointOnPoly(candidates[i],goal,point,nullptr))) continue;
            float score = std::hypot(point[0]-goal[0],point[2]-goal[2])*10000 + std::abs(point[1]-goal[1]);
            if (score >= best) continue;
            dtPolyRef trial[1024]; int length = 0;
            auto result = query.findPath(first,candidates[i],begin,point,&filter,trial,&length,1024);
            if (dtStatusFailed(result) || !length || trial[length-1] != candidates[i] || (result & DT_PARTIAL_RESULT)) continue;
            bool walking = true;
            for (int j = 0; j < length; ++j)
            {
                dtMeshTile const* routeTile; dtPoly const* poly;
                if (dtStatusFailed(mesh.getTileAndPolyByRef(trial[j],&routeTile,&poly))
                    || poly->getType() == DT_POLYTYPE_OFFMESH_CONNECTION) walking = false;
            }
            if (!walking) continue;
            best = score; last = candidates[i]; count = length;
            std::copy(trial,trial+length,corridor); std::copy(point,point+3,end);
        }
        if (!last)
            throw std::runtime_error("no connected walkable route");
        float points[3*256]; unsigned char flags[256]; dtPolyRef refs[256]; int pointsCount = 0;
        status = query.findStraightPath(begin,end,corridor,count,points,flags,refs,&pointsCount,256);
        if (dtStatusFailed(status) || (status & DT_BUFFER_TOO_SMALL)) throw std::runtime_error("ground route exceeds point budget");
        std::cout << std::setprecision(9) << "{\"schema\":\"public_ground_navmesh_route_v1\",\"loaded_tiles\":" << loaded
            << ",\"ground_only\":true,\"complete\":true,\"points\":[";
        for (int i = 0; i < pointsCount; ++i)
        {
            if (i) std::cout << ',';
            std::cout << '[' << points[3*i+2] << ',' << points[3*i] << ',' << points[3*i+1] << ']';
        }
        std::cout << "]}\n";
    }
    catch (std::exception const& error) { std::cerr << error.what() << '\n'; return 1; }
}
