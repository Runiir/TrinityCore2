"""Run the actual native swap function and its SQL across the removal interleave."""
import re
import sqlite3
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
HANDLER = ROOT / 'src/server/game/Handlers/PetHandler.cpp'
DATABASE = ROOT / 'src/server/database/Database/Implementation/CharacterDatabase.cpp'

STUBS = r'''
#include <cstdint>
#include <iostream>
#include <memory>
#include <vector>
using uint32 = uint32_t; using uint64 = uint64_t; using uint8 = uint8_t;
enum {CHAR_UPD_CHAR_PET_SLOT_BY_SLOT, CHAR_UPD_CHAR_PET_SLOT_BY_ID};
enum {PET_SAVE_DISMISS, STABLE_SUCCESS_STABLE};
struct Statement {
    int kind; uint64 values[3]{};
    void setUInt32(int i, uint32 v) { values[i]=v; }
    void setUInt64(int i, uint64 v) { values[i]=v; }
    void execute() {
        std::cout << "sql " << kind << ' ' << values[0] << ' '
                  << values[1] << ' ' << values[2] << '\n';
    }
};
using CharacterDatabasePreparedStatement = Statement;
struct Transaction {
    std::vector<std::unique_ptr<Statement>> statements;
    void Append(Statement* s) { statements.emplace_back(s); }
};
using CharacterDatabaseTransaction = std::shared_ptr<Transaction>;
struct Database {
    CharacterDatabaseTransaction BeginTransaction() { return std::make_shared<Transaction>(); }
    Statement* GetPreparedStatement(int kind) { return new Statement{kind}; }
    void CommitTransaction(CharacterDatabaseTransaction t) {
        for (auto& s:t->statements) s->execute();
    }
} CharacterDatabase;
struct PlayerPetData { uint32 PetId; uint8 Slot; };
struct Pet {
    uint32 id; uint8 slot;
    Pet* GetCharmInfo() { return this; }
    uint32 GetPetNumber() { return id; }
    void SetSlot(uint8 s) { slot=s; }
};
struct Guid { uint64 GetCounter() { return 6; } };
struct Player {
    PlayerPetData a{4,0},b{6,5}; Pet active; bool present;
    Player(int n):active{uint32(n),uint8(n==4?0:5)},present(n!=0) {}
    Pet* GetPet() { return present?&active:nullptr; }
    PlayerPetData* GetPlayerPetDataById(uint32 n) { return n==4?&a:&b; }
    PlayerPetData* GetPlayerPetDataBySlot(uint8 s) { return a.Slot==s?&a:b.Slot==s?&b:nullptr; }
    Guid GetGUID() { return {}; }
    void RemovePet(Pet* p, int) {
        // SavePetToDB commits the runtime pet before the outer queued transaction.
        Statement s{CHAR_UPD_CHAR_PET_SLOT_BY_ID,{p->slot,6,p->id}};
        s.execute(); present=false;
    }
};
struct WorldSession {
    Player* _player;
    void UpdatePetSlot(uint32, uint8, uint8);
    void SendPetSlotUpdated(uint32 a,uint32 as,uint32 b,uint32 bs) {
        std::cout << "updated " << a << ' ' << as << ' ' << b << ' ' << bs << '\n';
    }
    void SendStableResult(int) { std::cout << "success\n"; }
};
'''
MAIN = r'''
int main(int argc,char** argv) {
    Player p(std::stoi(argv[1])); WorldSession s{&p}; s.UpdatePetSlot(4,0,5);
    std::cout << "memory " << int(p.a.Slot) << ' ' << int(p.b.Slot) << ' ' << p.present << '\n';
}
'''


@pytest.fixture(scope='module')
def compiled(tmp_path_factory):
    text = HANDLER.read_text()
    start = text.index('void WorldSession::UpdatePetSlot(')
    function = text[start:text.index('void WorldSession::SendPetSlotUpdated(', start)]
    directory = tmp_path_factory.mktemp('native_slot_sql')
    binaries = []
    for label, body in [('fixed', function), ('broken', function.replace(
        'GetPreparedStatement(CHAR_UPD_CHAR_PET_SLOT_BY_ID)',
        'GetPreparedStatement(CHAR_UPD_CHAR_PET_SLOT_BY_SLOT)', 1).replace(
        'stmt->setUInt32(2, petNumberB)', 'stmt->setUInt32(2, newPetSlot)', 1))]:
        source, binary = directory / (label + '.cpp'), directory / label
        source.write_text(STUBS + body + MAIN)
        subprocess.run(['g++', '-std=c++17', '-O0', str(source), '-o', str(binary)],
                       check=True, capture_output=True, text=True)
        binaries.append(binary)
    return binaries


def saved_slots(binary, active):
    statements = dict(re.findall(r'PrepareStatement\((CHAR_UPD_CHAR_PET_SLOT_BY_(?:SLOT|ID)), "([^"]+)"',
                                  DATABASE.read_text()))
    connection = sqlite3.connect(':memory:')
    connection.execute('CREATE TABLE character_pet (id INTEGER, owner INTEGER, slot INTEGER)')
    connection.executemany('INSERT INTO character_pet VALUES (?,?,?)',
                          [(4,6,0),(6,6,5),(7,9,5),(8,6,9)])
    output = subprocess.check_output([str(binary), str(active)], text=True).splitlines()
    for line in output:
        if line.startswith('sql '):
            _, kind, *values = line.split()
            key = 'CHAR_UPD_CHAR_PET_SLOT_BY_' + ('SLOT' if kind == '0' else 'ID')
            connection.execute(statements[key], tuple(map(int, values)))
    assert output[-3:] == ['updated 4 5 6 0', 'success', 'memory 5 0 0']
    return connection.execute('SELECT id,owner,slot FROM character_pet ORDER BY id').fetchall()


@pytest.mark.parametrize('active', [4,6,0])
def test_saved_occupied_swap_preserves_both_ids_and_unrelated_rows(compiled, active):
    assert saved_slots(compiled[0], active) == [(4,6,5),(6,6,0),(7,9,5),(8,6,9)]


def test_previous_slot_predicate_reproduces_live_duplicate_after_active_a_save(compiled):
    assert saved_slots(compiled[1], 4) == [(4,6,0),(6,6,0),(7,9,5),(8,6,9)]
