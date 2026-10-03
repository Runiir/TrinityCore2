"""Check native deposits against the cheap-item trace and modern rounding cases."""
import subprocess
from pathlib import Path


def test_native_auction_deposit_matches_modern_quote(tmp_path):
    repo = Path(__file__).resolve().parents[4]
    source = tmp_path / 'deposit.cpp'
    binary = tmp_path / 'deposit'
    source.write_text(r'''
#include "Client442AuctionDeposit.h"
#include <cassert>
#include <cstdint>
int main()
{
    struct Case { std::uint32_t price; std::uint64_t deposit; };
    Case cases[] = {{0,0}, {1,0}, {6,0}, {7,0}, {13,0}, {14,1},
                    {20,3}, {30,3}, {100,15}, {101,14}, {10000,1500},
                    {4294967295U,644245093}};
    for (auto item : cases)
    {
        assert(Client442AuctionDeposit::Calculate(item.price,43200,1)==item.deposit);
        assert(Client442AuctionDeposit::Calculate(item.price,86400,1)==item.deposit*2);
        assert(Client442AuctionDeposit::Calculate(item.price,172800,1)==item.deposit*4);
        assert(Client442AuctionDeposit::Calculate(item.price,86400,20)==item.deposit*40);
        assert(Client442AuctionDeposit::Calculate(item.price,86400,0)==0);
    }
    // Captured Recruit's Pants (one copper sell price), one day: quoted zero.
    assert(Client442AuctionDeposit::Calculate(1,86400,1)==0);
}
''')
    subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                    '-I', str(repo / 'src/server/game/AuctionHouse'), str(source),
                    '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
