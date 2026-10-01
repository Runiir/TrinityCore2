/*
* This file is part of the TrinityCore Project. See AUTHORS file for Copyright information
*
* This program is free software; you can redistribute it and/or modify it
* under the terms of the GNU General Public License as published by the
* Free Software Foundation; either version 2 of the License, or (at your
* option) any later version.
*
* This program is distributed in the hope that it will be useful, but WITHOUT
* ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
* FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
* more details.
*
* You should have received a copy of the GNU General Public License along
* with this program. If not, see <http://www.gnu.org/licenses/>.
*/

#include "SitePolygonGraph.h"
#include "Random.h"
#include <algorithm>

//===========================================================================//
//      CLASS BASE METHODS
//===========================================================================//

SitePolygonGraph::SitePolygonGraph()
{
    // Commons
    _arches      = 0;
    _nodes       = 0;
    _size_nodes  = 0;
    _size_arches = 0;
    _geometry    = SitePolygonGraphGeometry();

    // use current time as seed for random generator
    std::srand(std::time(0));
}

SitePolygonGraph::~SitePolygonGraph()
{
    // Mem. Leaks free
    if(!_nodes) return;
    delete[] _nodes;

    // Mem. Leaks free
    if(!_arches) return;
    delete[] _arches;
}

//===========================================================================//
//      ADD NEW NODE TO POOL
//===========================================================================//

bool SitePolygonGraph::add_node(const SitePolygonGraphNode &node)
{
    return add_node(node.getX(), node.getY());
}

bool SitePolygonGraph::add_node(const float &x, const float &y)
{
    if(!resize_nodes())
        return false;

    _nodes[_size_nodes - 1].setX(x);
    _nodes[_size_nodes - 1].setY(y);

    // Generate boundary rectangle
    generate_geometry();

    if(_size_nodes > 1)
        return this->merge_perimeter();

    return true;
}

//===========================================================================//
//      ADD NEW ARCH TO POOL
//===========================================================================//

bool SitePolygonGraph::add_arch(const SitePolygonGraphNode &nodeA, const SitePolygonGraphNode &nodeB, bool skip_check)
{
    SitePolygonGraphArch tmp;
    tmp.setA(nodeA);
    tmp.setB(nodeB);

    // Check selector
    bool check = skip_check ? true : generate_geometry_fragmentation(tmp);

    // CHECK FOR FRAGMENTATION
    if(check)
    {
        if(!resize_arches())
            return false;

        // SAVE ARCH AND RETURN
        _arches[_size_arches - 1].set(tmp);
    }
    else return false;

    // Force TRUE
    return true;
}

//===========================================================================//
//      FINALIZE CREATION OF POLYGON (GEOMETRY INSCRIBED)
//===========================================================================//

void SitePolygonGraph::finalize_polygon()
{
    // Sampling uses the actual ordered perimeter. Chords of a concave polygon
    // can run outside it, so generated arches cannot define valid find points.
}

//===========================================================================//
//      CALCULATE RANDOM POINT ON RANDOM ARCH FOR SPAWN POI
//===========================================================================//

SitePolygonGraphNode SitePolygonGraph::randomize_poi()
{
    if (_size_nodes < 3)
        return SitePolygonGraphNode();

    float minX = _nodes[0].getX(), maxX = minX;
    float minY = _nodes[0].getY(), maxY = minY;
    for (index_type i = 1; i < _size_nodes; ++i)
    {
        minX = std::min(minX, _nodes[i].getX());
        maxX = std::max(maxX, _nodes[i].getX());
        minY = std::min(minY, _nodes[i].getY());
        maxY = std::max(maxY, _nodes[i].getY());
    }

    for (unsigned attempt = 0; attempt < 4096; ++attempt)
    {
        SitePolygonGraphNode point;
        point.set(frand(minX, maxX), frand(minY, maxY));
        // Node coordinates are rounded. Test the stored point, not its input.
        if (contains(point.getX(), point.getY()))
            return point;
    }
    // A perimeter vertex is valid even for extremely narrow polygons. Never
    // return an unchecked chord or the default world origin after retrying.
    return _nodes[0];
}

bool SitePolygonGraph::contains(float x, float y) const
{
    if (_size_nodes < 3 || !std::isfinite(x) || !std::isfinite(y))
        return false;

    bool inside = false;
    for (index_type i = 0, j = _size_nodes - 1; i < _size_nodes; j = i++)
    {
        double ax = _nodes[j].getX(), ay = _nodes[j].getY();
        double bx = _nodes[i].getX(), by = _nodes[i].getY();
        double dx = bx - ax, dy = by - ay;
        double cross = dx * (y - ay) - dy * (x - ax);
        if (cross == 0.0 && x >= std::min(ax, bx) && x <= std::max(ax, bx)
            && y >= std::min(ay, by) && y <= std::max(ay, by))
            return true;
        if ((ay > y) != (by > y) && x < ax + (y - ay) * dx / dy)
            inside = !inside;
    }
    return inside;
}
