// Public static model collision only. No server session or character database.
#include "VMapManager2.h"
#include <cmath>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>

int main(int argc, char** argv)
{
    try
    {
        if (argc!=6) throw std::runtime_error("expected VMAP directory, map and XYZ");
        std::string directory=argv[1];
        if (!directory.ends_with('/')) directory+='/';
        unsigned int map=std::stoul(argv[2]);
        float x=std::stof(argv[3]),y=std::stof(argv[4]),z=std::stof(argv[5]);
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
        float height=manager.getHeight(map,x,y,z+300,600);
        std::cout << std::setprecision(9) << "{\"source\":\"public static VMAP model collision\",\"loaded_tiles\":"
            << loaded << ",\"collision_height\":";
        if (height>VMAP_INVALID_HEIGHT && std::isfinite(height)) std::cout << height;else std::cout << "null";
        std::cout << "}\n";
    }
    catch (std::exception const& error) { std::cerr << error.what() << '\n';return 1; }
}
