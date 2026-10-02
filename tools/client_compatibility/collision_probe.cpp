// Public static model collision only. No server session or character database.
#include "VMapManager2.h"
#include "ModelIgnoreFlags.h"
#include <cmath>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>

int main(int argc, char** argv)
{
    try
    {
        bool segment=argc==10 && std::string(argv[3])=="--segment";
        if (argc!=6 && !segment) throw std::runtime_error("expected VMAP directory, map and XYZ or --segment endpoints");
        std::string directory=argv[1];
        if (!directory.ends_with('/')) directory+='/';
        unsigned int map=std::stoul(argv[2]);
        int offset=segment?4:3;
        float x=std::stof(argv[offset]),y=std::stof(argv[offset+1]),z=std::stof(argv[offset+2]);
        if (!std::isfinite(x) || !std::isfinite(y) || !std::isfinite(z))
            throw std::runtime_error("invalid public collision position");
        int gx=int(std::floor(32-x/533.33333333f)),gy=int(std::floor(32-y/533.33333333f));
        VMAP::VMapManager2 manager;int loaded=0;
        for (int dx=-1;dx<=1;++dx) for (int dy=-1;dy<=1;++dy)
        {
            auto result=manager.loadMap(directory.c_str(),map,gx+dx,gy+dy);
            if (result==VMAP::LoadResult::Success) ++loaded;
            else if (result!=VMAP::LoadResult::FileNotFound)
                throw std::runtime_error("public collision tile failed to load");
        }
        if (!loaded) throw std::runtime_error("public collision tiles unavailable");
        if (segment)
        {
            float ex=std::stof(argv[7]),ey=std::stof(argv[8]),ez=std::stof(argv[9]);
            if (!std::isfinite(ex) || !std::isfinite(ey) || !std::isfinite(ez)
                || std::hypot(ex-x,ey-y)>45) throw std::runtime_error("invalid bounded collision segment");
            bool clear=manager.isInLineOfSight(map,x,y,z,ex,ey,ez,VMAP::ModelIgnoreFlags::Nothing);
            std::cout << "{\"source\":\"public static VMAP model collision\",\"clear\":"
                << (clear?"true":"false") << "}\n";
            return 0;
        }
        float height=manager.getHeight(map,x,y,z+300,600);
        std::cout << std::setprecision(9) << "{\"source\":\"public static VMAP model collision\",\"loaded_tiles\":"
            << loaded << ",\"collision_height\":";
        if (height>VMAP_INVALID_HEIGHT && std::isfinite(height)) std::cout << height;else std::cout << "null";
        float support=manager.getHeight(map,x,y,z+2,6);
        std::cout << ",\"support_height\":";
        if (support>VMAP_INVALID_HEIGHT && std::isfinite(support)) std::cout << support;else std::cout << "null";
        uint32 flags=0;int32 adt=0,root=0,group=0;float areaZ=z+2;
        bool hasArea=manager.getAreaInfo(map,x,y,areaZ,flags,adt,root,group);
        std::cout << ",\"area\":";
        if (hasArea) std::cout << "{\"floor_z\":" << areaZ << ",\"mogp_flags\":" << flags
            << ",\"adt_id\":" << adt << ",\"root_id\":" << root << ",\"group_id\":" << group << "}";
        else std::cout << "null";
        std::cout << "}\n";
    }
    catch (std::exception const& error) { std::cerr << error.what() << '\n';return 1; }
}
