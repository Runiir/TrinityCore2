"""Run the native pure calculation against the captured ten-item repair quote."""
import subprocess
from pathlib import Path


def test_native_repair_rounding_matches_quote_and_preserves_legacy(tmp_path):
    repo=Path(__file__).resolve().parents[4]
    source=tmp_path/'repair.cpp';binary=tmp_path/'repair'
    source.write_text(r'''
#include "ItemRepairCost.h"
#include <cassert>
int main()
{
    struct Item { unsigned lost, multiplier, legacy, modern; };
    Item items[] = {
        {9,755,16138,16138}, {9,767,16395,16395}, {16,755,28690,28690},
        {5,755,8966,8966}, {14,755,25103,25104}, {7,755,12552,12552},
        {6,755,10758,10759}, {6,755,10758,10759}, {12,1156,32946,32946},
        {8,54,1026,1026}
    };
    unsigned oldTotal=0, newTotal=0;
    for (auto item : items)
    {
        auto legacy=ItemRepairCost::Calculate(item.lost,item.multiplier,2.5f,.95f,1.f,false);
        auto modern=ItemRepairCost::Calculate(item.lost,item.multiplier,2.5f,.95f,1.f,true);
        assert(legacy==item.legacy && modern==item.modern);
        oldTotal+=legacy;newTotal+=modern;
    }
    assert(oldTotal==163332 && newTotal==163335);
    for (bool modern : {false,true})
    {
        assert(ItemRepairCost::Calculate(0,755,2.5f,.95f,1.f,modern)==0);
        assert(ItemRepairCost::Calculate(1,0,0.f,1.f,1.f,modern)==1);
        assert(ItemRepairCost::Calculate(1,1,1.f,1.f,0.f,modern)==1);
        assert(ItemRepairCost::Calculate(10,100,1.f,.9f,2.f,modern)==1800);
    }
    assert(ItemRepairCost::Calculate(1,1,1.5f,1.f,1.f,true)==2);
}
'''.replace('#include <cassert>','#include <cassert>\n#include <initializer_list>'))
    subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-I',str(repo/'src/server/game/Entities/Item'),str(source),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
