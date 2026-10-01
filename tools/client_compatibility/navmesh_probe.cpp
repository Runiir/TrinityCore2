// Read public static collision navigation tiles; no server or character DB.
#include "DetourAlloc.h"
#include "DetourNavMesh.h"
#include "DetourNavMeshQuery.h"
#include "DetourCommon.h"
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
#include <array>

struct TileHeader { uint32_t magic, detourVersion, version, size; uint8_t liquids, padding[3]; };
static_assert(sizeof(TileHeader) == 20);

// Use the actual detail triangle at a landing point. A coarse navigation
// polygon can average a gentle plane across a steep hillside.
float groundSlope(dtNavMesh const& mesh, dtPolyRef ref, float const* point)
{
    dtMeshTile const* tile; dtPoly const* poly;
    if (dtStatusFailed(mesh.getTileAndPolyByRef(ref,&tile,&poly))) return INFINITY;
    auto const& detail=tile->detailMeshes[poly-tile->polys];
    for (int i=0;i<detail.triCount;++i)
    {
        auto triangle=tile->detailTris+(detail.triBase+i)*4;
        float const* vertices[3];
        for (int j=0;j<3;++j)
            vertices[j]=triangle[j]<poly->vertCount ? tile->verts+poly->verts[triangle[j]]*3
                : tile->detailVerts+(detail.vertBase+triangle[j]-poly->vertCount)*3;
        float height;
        if (!dtClosestHeightPointTriangle(point,vertices[0],vertices[1],vertices[2],height)) continue;
        float u[3],v[3];
        for (int j=0;j<3;++j) { u[j]=vertices[1][j]-vertices[0][j];v[j]=vertices[2][j]-vertices[0][j]; }
        float nx=u[1]*v[2]-u[2]*v[1],ny=u[2]*v[0]-u[0]*v[2],nz=u[0]*v[1]-u[1]*v[0];
        return std::atan2(std::hypot(nx,nz),std::abs(ny))*180/3.14159265f;
    }
    return INFINITY;
}

int main(int argc, char** argv)
{
    try
    {
        bool below = argc == 7 && std::string(argv[3]) == "--ground-below";
        bool swimming = argc>3 && std::string(argv[3])=="--walk-swim";
        if (swimming) { for (int i=3;i<argc-1;++i) argv[i]=argv[i+1];--argc; }
        bool connectedLanding = argc == 11 && std::string(argv[3]) == "--landing";
        bool landing = connectedLanding || (argc == 8 && std::string(argv[3]) == "--landing");
        bool column = below || landing || (argc == 6 && std::string(argv[3]) == "--ground");
        float radius = landing ? std::stof(argv[7]) : 4.f;
        if (!std::isfinite(radius) || radius<=0 || radius>30) throw std::runtime_error("invalid landing radius");
        float maximumHeight = below ? std::stof(argv[6]) : INFINITY;
        if (!column && (argc<9 || argc>33 || (argc-9)%3))
            throw std::runtime_error("expected map, start XYZ, goal XYZ, optional observed feet XYZ");
        std::filesystem::path directory(argv[1]);
        int map = std::stoi(argv[2]);
        float start[3] = {std::stof(argv[column ? 5 : 4]), column ? 0.f : std::stof(argv[5]), std::stof(argv[column ? 4 : 3])};
        if (landing) start[1]=std::stof(argv[6]);
        float goal[3];
        if (column) std::copy(start,start+3,goal);
        else { goal[0]=std::stof(argv[7]); goal[1]=std::stof(argv[8]); goal[2]=std::stof(argv[6]); }
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
        if (column)
        {
            dtPolyRef origin=0;float originPoint[3];
            if (connectedLanding)
            {
                float player[3]={std::stof(argv[9]),std::stof(argv[10]),std::stof(argv[8])}, near[3]={4,8,4};
                query.findNearestPoly(player,near,&filter,&origin,originPoint);
                if (!origin) throw std::runtime_error("no public ground near landing origin");
            }
            float extents[3]={radius,landing ? 80.f : 2000.f,radius}, chosen[3]; dtPolyRef refs[4096]; int count=0;
            auto status=query.queryPolygons(goal,extents,&filter,refs,&count,4096);
            if (dtStatusFailed(status) || (status & DT_BUFFER_TOO_SMALL)) throw std::runtime_error("ground column query exceeds budget");
            float best=INFINITY, chosenSlope=0;
            for (int i=0;i<count;++i)
            {
                float point[3];
                if (dtStatusFailed(query.closestPointOnPoly(refs[i],goal,point,nullptr))) continue;
                if (point[1]>maximumHeight) continue;
                float horizontal=std::hypot(point[0]-goal[0],point[2]-goal[2]);
                // Trial 42's 38.7-degree detail surface never settled: the
                // modern mount slid off it and resumed flight three times.
                // Prefer standing terrain rather than merely walkable slopes.
                if (horizontal>radius || (landing && groundSlope(mesh,refs[i],point)>20.f)) continue;
                bool covered=false;
                if (landing) for (int j=0;j<count;++j)
                {
                    float above[3];
                    if (dtStatusFailed(query.closestPointOnPoly(refs[j],point,above,nullptr))) continue;
                    if (std::hypot(above[0]-point[0],above[2]-point[2])<.1f && above[1]>point[1]+.5f)
                    { covered=true;break; }
                }
                if (covered) continue; // Flat polygons under hills/roofs cannot be landed on.
                if (connectedLanding)
                {
                    dtPolyRef path[1024];int length=0;
                    auto status=query.findPath(origin,refs[i],originPoint,point,&filter,path,&length,1024);
                    if (dtStatusFailed(status) || !length || path[length-1]!=refs[i] || (status & DT_PARTIAL_RESULT)) continue;
                    bool groundOnly=true;
                    for (int k=0;k<length;++k)
                    {
                        dtMeshTile const* tile;dtPoly const* poly;
                        if (dtStatusFailed(mesh.getTileAndPolyByRef(path[k],&tile,&poly)) || poly->getType()!=DT_POLYTYPE_GROUND)
                            groundOnly=false;
                    }
                    if (!groundOnly) continue;
                }
                float score=horizontal*100000+(landing ? std::abs(point[1]-goal[1]) : -point[1]);
                if (score<best) { best=score; std::copy(point,point+3,chosen);chosenSlope=groundSlope(mesh,refs[i],point); }
            }
            if (!std::isfinite(best)) throw std::runtime_error("no public walkable ground in destination column");
            std::cout << std::setprecision(9) << "{\"source\":\"public_static_ground_navmesh\",\"position\":["
                << chosen[2] << ',' << chosen[0] << ',' << chosen[1] << "],\"detail_slope_degrees\":"
                << (std::isfinite(chosenSlope) ? chosenSlope : -1) << "}\n";
            return 0;
        }
        // Legacy MMAP ground admits 55-degree slopes. The owned client slid
        // down a connected 54-degree rock face. Exclude steep polygon planes
        // in this local copy; shared tiles and native-server navigation stay unchanged.
        int steep=0;
        for (int i=0;i<mesh.getMaxTiles();++i)
        {
            auto tile=static_cast<dtNavMesh const&>(mesh).getTile(i);
            if (!tile || !tile->header) continue;
            for (int j=0;j<tile->header->polyCount;++j)
            {
                auto const& poly=tile->polys[j];
                if (poly.getType()!=DT_POLYTYPE_GROUND || !(poly.flags&1) || poly.vertCount<3) continue;
                float nx=0,ny=0,nz=0;
                auto a=tile->verts+poly.verts[0]*3;
                for (int k=2;k<poly.vertCount;++k)
                {
                    auto b=tile->verts+poly.verts[k-1]*3; auto c=tile->verts+poly.verts[k]*3;
                    float u[3]={b[0]-a[0],b[1]-a[1],b[2]-a[2]},v[3]={c[0]-a[0],c[1]-a[1],c[2]-a[2]};
                    nx+=u[1]*v[2]-u[2]*v[1];ny+=u[2]*v[0]-u[0]*v[2];nz+=u[0]*v[1]-u[1]*v[0];
                }
                if (std::hypot(nx,nz)>std::abs(ny)*0.96f)
                {
                    mesh.setPolyFlags(mesh.getPolyRefBase(tile)|j,poly.flags|0x8000);++steep;
                }
            }
        }
        filter.setExcludeFlags(0x8000);
        // At Coilskar a coarse walking surface is 1.5 yards above the
        // observed client feet beside a solid wall. This is not an ordinary
        // step. Exclude that nearby raised surface in this local query and
        // approach the lower floor before following a route around it.
        dtPolyRef local[4096];int localCount=0,obstructed=0;
        std::vector<std::array<float,3>> observed{{start[0],start[1],start[2]}},avoided;
        for (int i=9;i<argc;i+=3)
            observed.push_back({std::stof(argv[i+1]),std::stof(argv[i+2]),std::stof(argv[i])});
        for (auto const& feet:observed)
        {
            bool mismatch=false;float feetExtents[3]={1,4,1};
            auto status=query.queryPolygons(feet.data(),feetExtents,&filter,local,&localCount,4096);
            if (dtStatusFailed(status) || (status & DT_BUFFER_TOO_SMALL)) throw std::runtime_error("feet query exceeds budget");
            for (int i=0;i<localCount;++i)
            {
                float point[3];query.closestPointOnPoly(local[i],feet.data(),point,nullptr);
                if (std::hypot(point[0]-feet[0],point[2]-feet[2])<.35f
                    && point[1]-feet[1]>1.25f && point[1]-feet[1]<4.f) mismatch=true;
            }
            if (!mismatch) continue;
            avoided.push_back(feet);
            float vicinity[3]={12,6,12};
            status=query.queryPolygons(feet.data(),vicinity,&filter,local,&localCount,4096);
            if (dtStatusFailed(status) || (status & DT_BUFFER_TOO_SMALL)) throw std::runtime_error("obstruction query exceeds budget");
            for (int i=0;i<localCount;++i)
            {
                float point[3];query.closestPointOnPoly(local[i],feet.data(),point,nullptr);
                if (std::hypot(point[0]-feet[0],point[2]-feet[2])>12.f
                    || point[1]-feet[1]<=.8f || point[1]-feet[1]>=4.f) continue;
                unsigned short flags;mesh.getPolyFlags(local[i],&flags);
                if (!(flags&0x4000)) { mesh.setPolyFlags(local[i],flags|0x4000);++obstructed; }
            }
        }
        filter.setExcludeFlags(0xc000);
        // MMapDefines.h: ground=1, water=4, magma/slime=8. Keep the
        // obstruction and landing queries on ground, allowing clean water
        // only for this explicitly requested walking corridor.
        dtQueryFilter dryFilter=filter;
        if (swimming) filter.setIncludeFlags(1|4);
        float startExtents[3] = {4,8,4}, goalExtents[3] = {4,40,4};
        dtPolyRef first = 0, last = 0; float begin[3], end[3];
        query.findNearestPoly(start,startExtents,&filter,&first,begin);
        if (!first) throw std::runtime_error("no walkable ground near player feet");
        // Telescope packets provide heading, not the unknown target's height.
        // Consider ground at every elevation in the local column, preferring
        // horizontal proximity and requiring a fully connected walking path.
        dtPolyRef candidates[256], corridor[1024]; int candidatesCount = 0, count = 0;
        auto status = query.queryPolygons(goal,goalExtents,&dryFilter,candidates,&candidatesCount,256);
        if (dtStatusFailed(status) || (status & DT_BUFFER_TOO_SMALL)) throw std::runtime_error("ground column exceeds query budget");
        float best = INFINITY;
        for (int i = 0; i < candidatesCount; ++i)
        {
            float point[3];
            if (dtStatusFailed(query.closestPointOnPoly(candidates[i],goal,point,nullptr))) continue;
            if (swimming)
            {
                // Ground polygons can also be pond floors. A ground flag
                // alone does not prove the endpoint is on a dry bank.
                dtQueryFilter waterFilter;waterFilter.setIncludeFlags(4);waterFilter.setExcludeFlags(0);
                dtPolyRef waterRefs[256];int waterCount=0;float column[3]={2,80,2};bool wet=false;
                auto waterStatus=query.queryPolygons(point,column,&waterFilter,waterRefs,&waterCount,256);
                if (dtStatusFailed(waterStatus) || (waterStatus & DT_BUFFER_TOO_SMALL))
                    throw std::runtime_error("water column exceeds query budget");
                for (int k=0;k<waterCount;++k)
                {
                    float surface[3];query.closestPointOnPoly(waterRefs[k],point,surface,nullptr);
                    if (std::hypot(surface[0]-point[0],surface[2]-point[2])<2.f && surface[1]>=point[1]-.3f)
                    { wet=true;break; }
                }
                if (wet) continue;
            }
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
        status = query.findStraightPath(begin,end,corridor,count,points,flags,refs,&pointsCount,256,
            swimming ? DT_STRAIGHTPATH_AREA_CROSSINGS : 0);
        if (dtStatusFailed(status) || (status & DT_BUFFER_TOO_SMALL)) throw std::runtime_error("ground route exceeds point budget");
        int water=0;
        for (int i=0;i<count;++i) { unsigned short terrain;mesh.getPolyFlags(corridor[i],&terrain);if (terrain&4) ++water; }
        std::cout << std::setprecision(9) << "{\"schema\":\"public_ground_navmesh_route_v1\",\"loaded_tiles\":" << loaded
            << ",\"ground_only\":" << (water ? "false" : "true") << ",\"water_polygons\":" << water
            << ",\"swimming_allowed\":" << (swimming ? "true" : "false") << ",\"goal_terrain\":\"ground\""
            << ",\"allowed_terrain_flags\":" << (swimming ? 5 : 1)
            << ",\"complete\":true,\"excluded_steep_polygons\":" << steep
            << ",\"excluded_obstructed_polygons\":" << obstructed << ",\"obstruction_origins\":[";
        for (size_t i=0;i<avoided.size();++i)
        {
            if (i) std::cout << ',';
            std::cout << '[' << avoided[i][2] << ',' << avoided[i][0] << ',' << avoided[i][1] << ']';
        }
        std::cout << "],\"points\":[";
        for (int i = 0; i < pointsCount; ++i)
        {
            if (i) std::cout << ',';
            std::cout << '[' << points[3*i+2] << ',' << points[3*i] << ',' << points[3*i+1] << ']';
        }
        std::cout << "]}\n";
    }
    catch (std::exception const& error) { std::cerr << error.what() << '\n'; return 1; }
}
