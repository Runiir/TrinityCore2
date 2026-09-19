from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/custom/world/2026_09_19_05_balance_primary_dot_density.sql"
BOT_DIR = ROOT / "src/server/game/Bots"
TARGET_PROFILE = 290
DOT_SPELLS = (8921, 5570)
SUNFIRE = 93402

PROFILE_COLUMNS = (
    "id",
    "class_id",
    "spec_tag",
    "role",
    "version",
    "source_note",
    "scope_note",
)
ACTION_COLUMNS = (
    "id",
    "profile_id",
    "sort_order",
    "spell_id",
    "category",
    "mechanic_tags",
    "damage_weight",
    "priority_bucket",
    "min_enemies",
    "max_enemies",
    "max_target_health_pct",
    "target_selector",
    "requires_instant_cast",
    "maintain_aura_id",
    "refresh_aura_below_ms",
    "enabled",
)


def _database(*, version: int = 2) -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.executescript(
        """
        CREATE TABLE bot_rotation_profile (
            id INTEGER PRIMARY KEY,
            class_id INTEGER NOT NULL,
            spec_tag TEXT NOT NULL,
            role TEXT NOT NULL,
            version INTEGER NOT NULL,
            source_note TEXT NOT NULL,
            scope_note TEXT NOT NULL
        );
        CREATE TABLE bot_rotation_action (
            id INTEGER PRIMARY KEY,
            profile_id INTEGER NOT NULL,
            sort_order INTEGER NOT NULL,
            spell_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            mechanic_tags TEXT NOT NULL,
            damage_weight REAL NOT NULL,
            priority_bucket INTEGER NOT NULL,
            min_enemies INTEGER NOT NULL,
            max_enemies INTEGER NOT NULL,
            max_target_health_pct REAL NOT NULL,
            target_selector TEXT NOT NULL,
            requires_instant_cast INTEGER NOT NULL,
            maintain_aura_id INTEGER NOT NULL,
            refresh_aura_below_ms INTEGER NOT NULL,
            enabled INTEGER NOT NULL
        );
        """
    )
    db.executemany(
        "INSERT INTO bot_rotation_profile VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (
                TARGET_PROFILE,
                11,
                "balance_druid",
                "dps",
                version,
                "all_spec_phase1_canonical_coverage",
                "canonical all-spec target",
            ),
            # Same class, different spec: the primary-dot density repair must
            # not leak into Feral's profile.
            (291, 11, "feral_druid_dps", "dps", 2, "feral_profile", "feral remains independent"),
            # Same class, different role: the role predicate remains exact.
            (292, 11, "balance_druid", "healer", 2, "healer_profile", "healer remains independent"),
            # Different class, same role: spell ids alone are insufficient.
            (293, 8, "fire", "dps", 2, "fire_profile", "fire remains independent"),
        ],
    )

    def action(action_id: int, profile_id: int, sort_order: int, spell_id: int, max_enemies: int, tags: str) -> tuple:
        return (
            action_id,
            profile_id,
            sort_order,
            spell_id,
            "dot" if spell_id in DOT_SPELLS or spell_id == SUNFIRE else "builder",
            tags,
            0.92 if spell_id in DOT_SPELLS else 0.83,
            1 if spell_id in DOT_SPELLS else 3,
            1,
            max_enemies,
            1.0,
            "enemy",
            0,
            spell_id if spell_id in (*DOT_SPELLS, SUNFIRE) else 0,
            3000 if spell_id in (*DOT_SPELLS, SUNFIRE) else 0,
            1,
        )

    db.executemany(
        "INSERT INTO bot_rotation_action VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            action(1, TARGET_PROFILE, 10, 8921, 1, "moonfire,dot"),
            action(2, TARGET_PROFILE, 20, 5570, 1, "insect_swarm,dot"),
            action(3, TARGET_PROFILE, 30, SUNFIRE, 0, "sunfire,dot"),
            action(4, TARGET_PROFILE, 60, 5176, 0, "wrath,eclipse"),
            action(5, 291, 10, 8921, 1, "feral_unrelated"),
            action(6, 292, 10, 5570, 1, "healer_unrelated"),
            action(7, 293, 10, 8921, 1, "fire_unrelated"),
        ],
    )
    return db


def _profiles(db: sqlite3.Connection) -> list[tuple]:
    return db.execute(
        f"SELECT {', '.join(PROFILE_COLUMNS)} FROM bot_rotation_profile ORDER BY id"
    ).fetchall()


def _actions(db: sqlite3.Connection) -> list[tuple]:
    return db.execute(
        f"SELECT {', '.join(ACTION_COLUMNS)} FROM bot_rotation_action ORDER BY id"
    ).fetchall()


def _action(db: sqlite3.Connection, action_id: int) -> tuple:
    return db.execute(
        f"SELECT {', '.join(ACTION_COLUMNS)} FROM bot_rotation_action WHERE id = ?",
        (action_id,),
    ).fetchone()


def _run_migration(db: sqlite3.Connection) -> None:
    db.executescript(MIGRATION.read_text(encoding="utf-8"))


def test_migration_is_idempotent_and_scoped_to_balance_primary_dots() -> None:
    db = _database()
    before_profiles = _profiles(db)
    before_actions = _actions(db)

    _run_migration(db)
    first_profiles = _profiles(db)
    first_actions = _actions(db)
    _run_migration(db)

    assert _profiles(db) == first_profiles
    assert _actions(db) == first_actions
    assert first_profiles[0][4:] == (
        3,
        "balance_druid_primary_dot_density_2026_09_19",
        "Primary Moonfire and Insect Swarm ignore density caps; native target, LOS, aura, cooldown, Eclipse, resource, and allow_multidot gates remain authoritative",
    )
    assert first_profiles[1:] == before_profiles[1:]

    before_by_id = {row[0]: row for row in before_actions}
    after_by_id = {row[0]: row for row in first_actions}
    for action_id in (1, 2):
        before = before_by_id[action_id]
        after = after_by_id[action_id]
        assert before[9] == 1 and after[9] == 0
        assert after[:9] == before[:9]
        assert after[10:] == before[10:]

    # Sunfire is already unlimited and remains byte-for-byte unchanged.  The
    # other Balance action and every neighboring profile row are unchanged too.
    assert after_by_id[3] == before_by_id[3]
    assert after_by_id[4] == before_by_id[4]
    assert first_actions[4:] == before_actions[4:]


def test_profile_version_is_at_least_three_without_downgrading_newer_rows() -> None:
    db = _database(version=7)
    _run_migration(db)
    assert db.execute(
        "SELECT version FROM bot_rotation_profile WHERE id = ?", (TARGET_PROFILE,)
    ).fetchone() == (7,)
    assert db.execute(
        "SELECT max_enemies FROM bot_rotation_action WHERE profile_id = ? AND spell_id IN (8921, 5570) ORDER BY spell_id",
        (TARGET_PROFILE,),
    ).fetchall() == [(0,), (0,)]


def _block(source: str, marker: str) -> str:
    start = source.index(marker)
    brace = source.index("{", start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def _function(source: str, marker: str) -> str:
    return _block(source, marker)


def _statement(source: str, marker: str) -> str:
    start = source.index(marker)
    return source[start : source.index(";", start) + 1]


def _compile_native_density_fixture(tmp_path: Path) -> None:
    resolver = (BOT_DIR / "BotWorldPopulationMgrCombatResolver.cpp").read_text(encoding="utf-8")
    combat_spell = (BOT_DIR / "BotWorldPopulationMgrCombatSpell.cpp").read_text(encoding="utf-8")
    controller = (BOT_DIR / "BotControllerCombat.cpp").read_text(encoding="utf-8")
    executor = (BOT_DIR / "BotActionExecutor.cpp").read_text(encoding="utf-8")
    moving = (BOT_DIR / "BotCastWhileMoving.h").read_text(encoding="utf-8")

    resolver_density = _block(
        resolver,
        "        if (candidate.Profile.MaxEnemies && hostileCount > candidate.Profile.MaxEnemies)",
    )
    combat_spell_density = _block(
        combat_spell,
        "        if (candidate.Profile.MaxEnemies && candidate.Profile.MaxEnemies < nearbyEnemyCount)",
    )
    controller_density = _block(
        controller,
        "        if (candidate.Profile.MaxEnemies && state.NearbyHostileCount > candidate.Profile.MaxEnemies)",
    )
    resolver_aura = _block(
        resolver,
        "        if (MaintainedProfileAuraBlocksRefresh(actionTarget, candidate.Profile))",
    )
    maintained_aura = _function(resolver, "bool MaintainedProfileAuraBlocksRefresh(")
    check_start = executor.index("BotActionResult BotActionExecutor::CheckHostileSpell")
    check_source = executor[check_start:]
    los_gate = _statement(check_source, "    if (!bot->IsWithinLOSInMap(target))")
    gcd_gate = _statement(
        check_source,
        "    if (bot->GetSpellHistory()->HasGlobalCooldown(spellInfo))",
    )
    ready_gate = _statement(
        check_source,
        "    if (!bot->GetSpellHistory()->IsReady(spellInfo))",
    )
    has_capability = _function(moving, "template <typename Caster>\nbool HasNativeCapability(")
    reject_moving = _function(moving, "template <typename Caster>\nbool RejectMovingCandidate(")

    assert resolver.index("candidate.Profile.MaxEnemies && hostileCount") < resolver.index(
        "MaintainedProfileAuraBlocksRefresh(actionTarget, candidate.Profile)"
    )
    assert "hostileCount" in resolver_density
    assert "nearbyEnemyCount" in combat_spell_density
    assert "state.NearbyHostileCount" in controller_density
    assert "candidate.RejectReason = \"maintain_aura_active\"" in resolver_aura
    assert "BotWorldPopulationMgr::ResolveProfileCombatAction" in resolver
    assert "ResolveProfileCombatAction(" in (ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateBotKernelFallback.cpp").read_text(encoding="utf-8")
    execution = (BOT_DIR / "BotWorldPopulationMgrCombatExecution.cpp").read_text(encoding="utf-8")
    fallback = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateBotKernelFallback.cpp").read_text(encoding="utf-8")
    assert "magmawProfile.AllowMultidot" in fallback
    assert "allowMultidot && !forbidArea" in execution
    assert "candidate.Profile.MaxEnemies" in resolver_density + combat_spell_density + controller_density

    source = tmp_path / "balance_density_native.cpp"
    binary = tmp_path / "balance_density_native"
    source.write_text(
        """
#include <cassert>
#include <cstdint>
#include <string>
using uint8 = unsigned char;
using uint32 = unsigned;
using int32 = int;
enum class BotActionResult { Ok, NoLineOfSight, GlobalCooldown, Cooldown };
enum { SPELL_AURA_CAST_WHILE_WALKING = 1 };
struct SpellInfo {};
struct Aura { int32 duration; int32 GetDuration() const { return duration; } };
struct BotActionProfileSpell {
    uint32 MaxEnemies = 0;
    uint32 MinEnemies = 1;
    uint32 MaintainAuraId = 0;
    uint32 RefreshAuraBelowMs = 0;
};
struct Unit {
    Aura const* aura = nullptr;
    Aura const* GetAura(uint32) const { return aura; }
};
struct Candidate {
    BotActionProfileSpell Profile;
    std::string RejectReason;
    uint32 SpellId = 0;
    uint32 TargetEntry = 0;
    bool PrimaryTargetValid = false;
    bool Moving = false;
    bool RequiresInstantCast = false;
    uint32 CastTimeMs = 0;
    bool AllowMultidot = false;
};
struct State { uint32 NearbyHostileCount = 1; };
struct SpellHistory {
    bool GlobalCooldown = false;
    bool Ready = true;
    bool HasGlobalCooldown(SpellInfo const*) const { return GlobalCooldown; }
    bool IsReady(SpellInfo const*) const { return Ready; }
};
struct Bot {
    bool LineOfSight = true;
    SpellHistory History;
    bool IsWithinLOSInMap(Unit const*) const { return LineOfSight; }
    SpellHistory const* GetSpellHistory() const { return &History; }
    bool HasAuraTypeWithAffectMask(int, SpellInfo const*) const { return false; }
};
"""
        + maintained_aura
        + """
bool ResolverDensity(Candidate& candidate, uint32 hostileCount) {
    for (int once = 0; once < 1; ++once) {
"""
        + resolver_density
        + """
    }
    return candidate.RejectReason.empty();
}
bool CombatSpellDensity(Candidate& candidate, uint32 nearbyEnemyCount) {
    for (int once = 0; once < 1; ++once) {
"""
        + combat_spell_density
        + """
    }
    return candidate.RejectReason.empty();
}
bool ControllerDensity(Candidate& candidate, State const& state) {
    for (int once = 0; once < 1; ++once) {
"""
        + controller_density
        + """
    }
    return candidate.RejectReason.empty();
}
bool ResolverAura(Unit const* actionTarget, Candidate& candidate) {
    for (int once = 0; once < 1; ++once) {
"""
        + resolver_aura
        + """
    }
    return candidate.RejectReason.empty();
}
BotActionResult NativeLineOfSight(Bot const* bot, Unit const* target) {
"""
        + los_gate
        + """
    return BotActionResult::Ok;
}
BotActionResult NativeCooldown(Bot const* bot, SpellInfo const* spellInfo) {
"""
        + gcd_gate
        + "\n"
        + ready_gate
        + """
    return BotActionResult::Ok;
}
namespace BotCastWhileMoving {
"""
        + has_capability
        + reject_moving
        + """
}
bool MovingInstantAdmitted(bool movementCompatibleOnly, bool castTime, bool channeled) {
    Bot bot;
    SpellInfo spell;
    return !BotCastWhileMoving::RejectMovingCandidate(
        &bot, &spell, movementCompatibleOnly, castTime, channeled);
}
int main() {
    Candidate dot;
    dot.SpellId = 8921;
    dot.TargetEntry = 42347; // live Magmaw head from the reviewed movement window
    dot.PrimaryTargetValid = true;
    dot.Moving = true;
    dot.RequiresInstantCast = true;
    dot.CastTimeMs = 0;
    dot.AllowMultidot = false; // the encounter caller keeps this runtime context
    dot.Profile.MaxEnemies = 0;
    assert(dot.TargetEntry == 42347 && dot.PrimaryTargetValid && dot.Moving);
    assert(dot.RequiresInstantCast && dot.CastTimeMs == 0 && !dot.AllowMultidot);
    assert(ResolverDensity(dot, 3));
    assert(CombatSpellDensity(dot, 3));
    State state{3};
    assert(ControllerDensity(dot, state));

    Candidate stale;
    stale.Profile.MaxEnemies = 1;
    assert(!ResolverDensity(stale, 3));
    assert(!CombatSpellDensity(stale, 3));
    assert(!ControllerDensity(stale, state));

    Aura targetAura{1000};
    Unit target{&targetAura};
    dot.Profile.MaintainAuraId = 8921;
    dot.Profile.RefreshAuraBelowMs = 3000;
    assert(ResolverAura(&target, dot));
    targetAura.duration = 6000;
    Candidate activeAura = dot;
    assert(!ResolverAura(&target, activeAura));

    Bot bot;
    SpellInfo spell;
    assert(NativeLineOfSight(&bot, &target) == BotActionResult::Ok);
    bot.LineOfSight = false;
    assert(NativeLineOfSight(&bot, &target) == BotActionResult::NoLineOfSight);
    bot.LineOfSight = true;
    assert(NativeCooldown(&bot, &spell) == BotActionResult::Ok);
    bot.History.GlobalCooldown = true;
    assert(NativeCooldown(&bot, &spell) == BotActionResult::GlobalCooldown);
    bot.History.GlobalCooldown = false;
    bot.History.Ready = false;
    assert(NativeCooldown(&bot, &spell) == BotActionResult::Cooldown);

    // The traced candidate is instant while moving; an uncovered cast-time
    // candidate remains rejected by the native movement helper.
    assert(MovingInstantAdmitted(true, false, false));
    assert(!MovingInstantAdmitted(true, true, false));
}
""",
        encoding="utf-8",
    )
    subprocess.run(
        [
            "c++",
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
    )
    subprocess.run([str(binary)], check=True)


def test_native_density_consumers_and_candidate_gates_are_executed(tmp_path: Path) -> None:
    _compile_native_density_fixture(tmp_path)
