// Exercise the actual native sampler against an independent winding test.
#include "SitePolygonGraph.h"
#include "Random.h"
#include <iostream>
#include <random>
#include <vector>
#include <cassert>

static std::mt19937 generator(20261001);
float frand(float low, float high) { return std::uniform_real_distribution<float>(low, high)(generator); }
uint32 urand(uint32 low, uint32 high) { return std::uniform_int_distribution<uint32>(low, high)(generator); }

bool referenceContains(std::vector<SitePolygonGraphNode> const& nodes, float x, float y)
{
    int winding = 0;
    for (std::size_t i = 0; i < nodes.size(); ++i)
    {
        auto const& a = nodes[i]; auto const& b = nodes[(i + 1) % nodes.size()];
        double dx = b.getX() - a.getX(), dy = b.getY() - a.getY();
        double cross = dx * (y - a.getY()) - dy * (x - a.getX());
        if (std::abs(cross) < 0.001 && x >= std::min(a.getX(), b.getX()) && x <= std::max(a.getX(), b.getX())
            && y >= std::min(a.getY(), b.getY()) && y <= std::max(a.getY(), b.getY())) return true;
        if (a.getY() <= y && b.getY() > y && cross > 0) ++winding;
        if (a.getY() > y && b.getY() <= y && cross < 0) --winding;
    }
    return winding != 0;
}

int main()
{
    unsigned cases, samples; std::cin >> cases >> samples;
    unsigned invalid = 0, total = 0;
    for (unsigned c = 0; c < cases; ++c)
    {
        unsigned id, count; std::cin >> id >> count;
        SitePolygonGraph polygon; std::vector<SitePolygonGraphNode> nodes;
        for (unsigned i = 0; i < count; ++i)
        {
            float x,y; std::cin >> x >> y;
            SitePolygonGraphNode point; point.set(x,y); nodes.push_back(point); polygon.add_node(point);
        }
        polygon.finalize_polygon(); unsigned failures = 0;
        for (unsigned n = 0; n < samples; ++n)
        {
            auto point = polygon.randomize_poi();
            if (!referenceContains(nodes, point.getX(), point.getY())) ++failures;
            ++total;
        }
        invalid += failures;
        if (failures) std::cerr << "site " << id << " outside " << failures << '/' << samples << '\n';
#ifdef TEST_CONTAINS
        assert(!polygon.contains(INFINITY, 0));
        assert(polygon.contains(nodes[0].getX(), nodes[0].getY()));
#endif
    }
    std::cout << "{\"samples\":" << total << ",\"outside\":" << invalid << "}\n";
    return invalid ? 1 : 0;
}
