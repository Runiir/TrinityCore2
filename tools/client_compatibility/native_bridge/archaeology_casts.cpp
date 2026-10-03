#include "archaeology.hpp"
#include <unordered_set>

namespace bridge
{
Array archaeology_weights(Reader &r, unsigned count)
{
    if (count > 2) throw std::runtime_error("archaeology supports currency and optional keystone weights");
    static std::unordered_set<unsigned> const currencies{384,385,393,394,397,398,399,400,401};
    static std::unordered_set<unsigned> const keystones{52843,63127,63128,64392,64394,64395,64396,64397};
    Array weights;
    unsigned types=0;
    for (unsigned i=0;i<count;++i)
    {
        auto type=r.bits(2);r.align();
        auto id=r.take<std::int32_t>();auto quantity=r.take<std::uint32_t>();
        if ((type!=1 && type!=2) || (types&(1u<<type)) || id<=0 || !quantity ||
            (type==1 && (!currencies.contains(id) || quantity>200)) ||
            (type==2 && (!keystones.contains(id) || quantity>3)))
            throw std::runtime_error("unsupported archaeology weight");
        types|=1u<<type;
        weights.push_back(Array{type,id,quantity});
    }
    if (count && !(types&2u)) throw std::runtime_error("archaeology requires a fragment weight");
    return weights;
}
}
