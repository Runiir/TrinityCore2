from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/custom/world/2026_09_09_07_fire_moving_scorch.sql"
RESOLVER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatResolver.cpp"

FALLBACK_TAGS = "scorch,firestarter,moving_filler,resource_fallback"
MOVING_TAGS = "scorch,firestarter,moving_filler,movement_only"


def make_profile_db() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(
        """
        CREATE TABLE bot_rotation_profile (
            id INTEGER PRIMARY KEY, class_id INTEGER, spec_tag TEXT,
            role TEXT, enabled INTEGER
        );
        CREATE TABLE bot_rotation_action (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id INTEGER NOT NULL, sort_order INTEGER DEFAULT 0,
            spell_id INTEGER DEFAULT 0, category TEXT NOT NULL,
            mechanic_tags TEXT DEFAULT '', damage_weight REAL DEFAULT 0,
            healing_weight REAL DEFAULT 0, threat_weight REAL DEFAULT 0,
            mitigation_weight REAL DEFAULT 0, survival_weight REAL DEFAULT 0,
            movement_weight REAL DEFAULT 0, progression_weight REAL DEFAULT 0,
            profession_weight REAL DEFAULT 0, priority_bucket INTEGER DEFAULT 5,
            min_enemies INTEGER DEFAULT 1, max_enemies INTEGER DEFAULT 0,
            min_target_health_pct REAL DEFAULT 0,
            max_target_health_pct REAL DEFAULT 1,
            min_self_health_pct REAL DEFAULT 0,
            max_self_health_pct REAL DEFAULT 1,
            required_self_aura INTEGER DEFAULT 0,
            forbidden_self_aura INTEGER DEFAULT 0,
            required_target_aura INTEGER DEFAULT 0,
            forbidden_target_aura INTEGER DEFAULT 0,
            requires_interruptible_target INTEGER DEFAULT 0,
            requires_target_not_victim INTEGER DEFAULT 0,
            requires_target_victim INTEGER DEFAULT 0,
            requires_melee_range INTEGER DEFAULT 0,
            requires_ranged_range INTEGER DEFAULT 0,
            target_selector TEXT DEFAULT 'enemy',
            movement_directive TEXT DEFAULT '', auto_attack_mode TEXT DEFAULT '',
            min_range REAL DEFAULT 0, max_range REAL DEFAULT 0,
            requires_instant_cast INTEGER DEFAULT 0,
            max_cast_time_ms INTEGER DEFAULT 0, maintain_aura_id INTEGER DEFAULT 0,
            refresh_aura_below_ms INTEGER DEFAULT 0,
            min_injured_players INTEGER DEFAULT 0,
            max_injured_players INTEGER DEFAULT 0, injured_health_pct REAL DEFAULT 1,
            min_mana_pct REAL DEFAULT 0, max_mana_pct REAL DEFAULT 1,
            min_primary_power_pct REAL DEFAULT 0,
            max_primary_power_pct REAL DEFAULT 1,
            min_attackers INTEGER DEFAULT 0, max_attackers INTEGER DEFAULT 0,
            requires_stationary INTEGER DEFAULT 0, requires_moving INTEGER DEFAULT 0,
            required_self_aura_stacks INTEGER DEFAULT 0,
            max_self_aura_stacks INTEGER DEFAULT 0,
            min_self_aura_remaining_ms INTEGER DEFAULT 0,
            max_self_aura_remaining_ms INTEGER DEFAULT 0,
            required_owned_target_aura INTEGER DEFAULT 0,
            forbidden_owned_target_aura INTEGER DEFAULT 0,
            min_combo_points INTEGER DEFAULT 0, max_combo_points INTEGER DEFAULT 0,
            min_ready_runes INTEGER DEFAULT 0,
            required_shapeshift_form INTEGER DEFAULT 0,
            requires_pet INTEGER DEFAULT 0, forbids_pet INTEGER DEFAULT 0,
            required_main_hand_enchant INTEGER DEFAULT 0,
            required_off_hand_enchant INTEGER DEFAULT 0,
            cooldown_group TEXT DEFAULT '', target_creature_type_mask INTEGER DEFAULT 0,
            requires_ground_target INTEGER DEFAULT 0,
            min_hostile_target_health_pct REAL DEFAULT 0,
            required_self_aura_charges INTEGER DEFAULT 0,
            max_self_aura_charges INTEGER DEFAULT 0,
            min_owned_target_aura_remaining_ms INTEGER DEFAULT 0,
            max_hostile_target_health_pct REAL DEFAULT 0,
            enabled INTEGER DEFAULT 1
        );
        INSERT INTO bot_rotation_profile VALUES
            (1, 8, 'fire', 'dps', 1),
            (2, 8, 'fire', 'dps', 0),
            (3, 8, 'arcane', 'dps', 1),
            (4, 7, 'fire', 'dps', 1),
            (5, 8, 'fire', 'healer', 1);
        """
    )
    db.execute(
        """
        INSERT INTO bot_rotation_action
          (profile_id, sort_order, spell_id, category, mechanic_tags,
           damage_weight, movement_weight, priority_bucket, min_enemies,
           max_enemies, target_selector, movement_directive, auto_attack_mode,
           min_range, max_range, min_mana_pct, max_mana_pct,
           min_primary_power_pct, max_primary_power_pct, min_attackers,
           max_attackers, requires_stationary, requires_moving, cooldown_group,
           enabled)
        VALUES
          (1, 55, 2948, 'resource_generator', ?, 0.74, 0.17, 5, 1, 1,
           'enemy', 'ranged', 'none', 0, 35, 0.03, 0.40, 0.02, 0.98,
           0, 3, 0, 0, 'fire_filler', 1)
        """,
        (FALLBACK_TAGS,),
    )
    db.executemany(
        """
        INSERT INTO bot_rotation_action
          (profile_id, sort_order, spell_id, category, mechanic_tags,
           damage_weight, priority_bucket, target_selector, max_range,
           required_self_aura, forbidden_owned_target_aura, enabled)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'enemy', 35, ?, ?, 1)
        """,
        [
            (1, 20, 44457, "dot", "living_bomb,maintain_debuff", 0.98, 1, 0, 44457),
            (1, 30, 92315, "spender", "pyroblast,hot_streak_only,instant_proc", 1.00, 1, 48108, 0),
            (1, 50, 133, "builder", "fireball,filler", 0.78, 4, 0, 0),
            (1, 60, 2136, "spender", "fire_blast,instant", 0.70, 6, 0, 0),
        ],
    )
    for profile_id, tag in ((2, "disabled"), (3, "other_spec"), (4, "other_class"), (5, "other_role")):
        db.execute(
            "INSERT INTO bot_rotation_action "
            "(profile_id, sort_order, spell_id, category, mechanic_tags, max_mana_pct) "
            "VALUES (?, 55, 2948, 'resource_generator', ?, 0.40)",
            (profile_id, tag),
        )
    return db


def semantic_rows(db: sqlite3.Connection, profile_id: int = 1) -> list[tuple[object, ...]]:
    columns = [row[1] for row in db.execute("PRAGMA table_info(bot_rotation_action)") if row[1] != "id"]
    return db.execute(
        f"SELECT {', '.join(columns)} FROM bot_rotation_action "
        f"WHERE profile_id = ? ORDER BY priority_bucket, sort_order, spell_id, mechanic_tags",
        (profile_id,),
    ).fetchall()


def test_scoped_migration_clones_all_typed_gates_and_replays_idempotently() -> None:
    db = make_profile_db()
    migration = MIGRATION.read_text(encoding="utf-8")
    untouched = {profile_id: semantic_rows(db, profile_id) for profile_id in range(2, 6)}

    db.executescript(migration)
    once = semantic_rows(db)
    db.executescript(migration)
    assert semantic_rows(db) == once
    assert {profile_id: semantic_rows(db, profile_id) for profile_id in range(2, 6)} == untouched

    scorch = db.execute(
        "SELECT * FROM bot_rotation_action WHERE profile_id = 1 AND spell_id = 2948 "
        "ORDER BY sort_order"
    ).fetchall()
    assert len(scorch) == 2
    fallback, moving = scorch
    assert (fallback["sort_order"], fallback["mechanic_tags"], fallback["max_mana_pct"],
            fallback["requires_stationary"], fallback["requires_moving"]) == (
        55, FALLBACK_TAGS, 0.40, 0, 0
    )
    assert (moving["sort_order"], moving["mechanic_tags"], moving["max_mana_pct"],
            moving["requires_stationary"], moving["requires_moving"]) == (
        56, MOVING_TAGS, 1.00, 0, 1
    )
    intentional = {"id", "sort_order", "mechanic_tags", "max_mana_pct", "requires_moving"}
    for key in fallback.keys():
        if key not in intentional:
            assert moving[key] == fallback[key], key

    for line in migration.splitlines():
        if line.lstrip().startswith("--"):
            assert line.lstrip().startswith("-- ")


def test_production_movement_gate_and_ranking_replay(tmp_path: Path) -> None:
    db = make_profile_db()
    db.executescript(MIGRATION.read_text(encoding="utf-8"))
    rows = {
        (row["spell_id"], row["mechanic_tags"]): row
        for row in db.execute("SELECT * FROM bot_rotation_action WHERE profile_id = 1")
    }
    moving = rows[(2948, MOVING_TAGS)]
    fallback = rows[(2948, FALLBACK_TAGS)]

    resolver_source = RESOLVER.read_text(encoding="utf-8")
    comparator_start = resolver_source.index("    auto candidatePreferred =")
    comparator_end = resolver_source.index("\n    };", comparator_start) + 7
    comparator = resolver_source[comparator_start:comparator_end].replace(
        "BotActionCandidate", "Candidate"
    )
    source = tmp_path / "fire_moving_scorch.cpp"
    binary = tmp_path / "fire_moving_scorch"
    program = r'''
#include "Bots/BotCastWhileMoving.h"

#include <cassert>
#include <string>
#include <vector>

class SpellInfo { public: unsigned Id = 0; };
struct Caster
{
    bool Firestarter = false;
    bool HasAuraTypeWithAffectMask(AuraType auraType, SpellInfo const* spell) const
    {
        return Firestarter && spell && spell->Id == 2948
            && auraType == SPELL_AURA_CAST_WHILE_WALKING;
    }
};
struct Candidate
{
    unsigned SpellId = 0;
    std::string Tags;
    std::string RejectReason;
    bool CastTime = false;
    bool RequiresMoving = false;
    bool RequiresAura = false;
    bool MaintenanceBlocked = false;
    bool GlobalCooldown = false;
    bool CooldownReady = true;
    bool EnoughResource = true;
    bool InRange = true;
    bool InLineOfSight = true;
    float MinMana = 0.0f;
    float MaxMana = 1.0f;
    struct { unsigned PriorityBucket = 5; unsigned SortOrder = 0; } Profile;
    float Score = 0.0f;
    unsigned ActionId = 0;
};

void Evaluate(std::vector<Candidate>& candidates, Caster const& caster,
    bool moving, float mana, bool hotStreak)
{
    for (Candidate& candidate : candidates)
    {
        if (candidate.GlobalCooldown) candidate.RejectReason = "global_cooldown";
        else if (!candidate.CooldownReady) candidate.RejectReason = "cooldown_not_ready";
        else if (!candidate.EnoughResource) candidate.RejectReason = "insufficient_resource";
        else if (!candidate.InRange) candidate.RejectReason = "out_of_range";
        else if (!candidate.InLineOfSight) candidate.RejectReason = "line_of_sight";
        else if (candidate.RequiresAura && !hotStreak) candidate.RejectReason = "missing_self_aura";
        else if (candidate.MaintenanceBlocked) candidate.RejectReason = "maintain_aura_active";
        else if (mana < candidate.MinMana || mana > candidate.MaxMana) candidate.RejectReason = "mana_gate";
        else if (candidate.RequiresMoving && !moving) candidate.RejectReason = "movement_gate";
        if (!candidate.RejectReason.empty())
            continue;

        SpellInfo info{candidate.SpellId};
        if (BotCastWhileMoving::RejectMovingCandidate(
                &caster, &info, moving, candidate.CastTime, false))
            candidate.RejectReason = "movement_requires_instant_action";
    }
}

Candidate* Find(std::vector<Candidate>& candidates, unsigned spell, std::string const& tags = {})
{
    for (Candidate& candidate : candidates)
        if (candidate.SpellId == spell && (tags.empty() || candidate.Tags == tags))
            return &candidate;
    return nullptr;
}

unsigned SelectedSpell(std::vector<Candidate> const& candidates)
{
NATIVE_CANDIDATE_COMPARATOR
    Candidate const* selected = nullptr;
    for (Candidate const& candidate : candidates)
        if (candidate.RejectReason.empty() && candidatePreferred(candidate, selected))
            selected = &candidate;
    return selected ? selected->SpellId : 0;
}

std::vector<Candidate> Rows()
{
    return {
        {44457, "living_bomb", "", false, false, false, true, false, true, true, true, true,
            0.0f, 1.0f, {1, 20}, 1.93f, 44457},
        {92315, "hot_streak", "", false, false, true, false, false, true, true, true, true,
            0.0f, 1.0f, {1, 30}, 1.97f, 92315},
        {133, "fireball", "", true, false, false, false, false, true, true, true, true,
            0.0f, 1.0f, {4, 50}, 1.44f, 133},
        {2948, "FALLBACK_TAGS", "", true, false, false, false, false, true, true, true, true,
            FALLBACK_MIN_MANA, FALLBACK_MAX_MANA, {FALLBACK_BUCKET, FALLBACK_SORT}, 1.33f, 2948},
        {2948, "MOVING_TAGS", "", true, true, false, false, false, true, true, true, true,
            MOVING_MIN_MANA, MOVING_MAX_MANA, {MOVING_BUCKET, MOVING_SORT}, 1.33f, 2948},
        {2136, "fire_blast", "", false, false, false, false, false, true, true, true, true,
            0.0f, 1.0f, {6, 60}, 1.22f, 2136},
    };
}

int main()
{
    // Captured actor 30006 BODY state: moving at high mana, maintenance done,
    // Fireball movement-blocked. Firestarter makes only moving Scorch legal.
    auto captured = Rows();
    Evaluate(captured, {true}, true, 0.75f, false);
    assert(Find(captured, 133)->RejectReason == "movement_requires_instant_action");
    assert(Find(captured, 2948, "FALLBACK_TAGS")->RejectReason == "mana_gate");
    assert(Find(captured, 2948, "MOVING_TAGS")->RejectReason.empty());
    assert(SelectedSpell(captured) == 2948);

    auto stationary = Rows();
    Evaluate(stationary, {true}, false, 0.75f, false);
    assert(Find(stationary, 2948, "MOVING_TAGS")->RejectReason == "movement_gate");
    assert(SelectedSpell(stationary) == 133);

    auto lowMana = Rows();
    Evaluate(lowMana, {true}, false, 0.35f, false);
    assert(Find(lowMana, 2948, "FALLBACK_TAGS")->RejectReason.empty());
    assert(Find(lowMana, 2948, "MOVING_TAGS")->RejectReason == "movement_gate");

    auto noCapability = Rows();
    Evaluate(noCapability, {false}, true, 0.75f, false);
    assert(Find(noCapability, 2948, "MOVING_TAGS")->RejectReason
        == "movement_requires_instant_action");
    assert(SelectedSpell(noCapability) == 2136);

    auto hotStreak = Rows();
    Evaluate(hotStreak, {true}, true, 0.75f, true);
    assert(SelectedSpell(hotStreak) == 92315);

    auto maintenance = Rows();
    Find(maintenance, 44457)->MaintenanceBlocked = false;
    Evaluate(maintenance, {true}, true, 0.75f, false);
    assert(SelectedSpell(maintenance) == 44457);

    for (std::string reason : {"global_cooldown", "cooldown_not_ready",
            "insufficient_resource", "out_of_range", "line_of_sight"})
    {
        auto gated = Rows();
        Candidate* row = Find(gated, 2948, "MOVING_TAGS");
        if (reason == "global_cooldown") row->GlobalCooldown = true;
        else if (reason == "cooldown_not_ready") row->CooldownReady = false;
        else if (reason == "insufficient_resource") row->EnoughResource = false;
        else if (reason == "out_of_range") row->InRange = false;
        else row->InLineOfSight = false;
        Evaluate(gated, {true}, true, 0.75f, false);
        assert(row->RejectReason == reason);
    }
}
'''
    substitutions = {
        "NATIVE_CANDIDATE_COMPARATOR": comparator,
        "FALLBACK_TAGS": FALLBACK_TAGS,
        "MOVING_TAGS": MOVING_TAGS,
        "FALLBACK_MIN_MANA": f'{fallback["min_mana_pct"]:.2f}f',
        "FALLBACK_MAX_MANA": f'{fallback["max_mana_pct"]:.2f}f',
        "FALLBACK_BUCKET": str(fallback["priority_bucket"]),
        "FALLBACK_SORT": str(fallback["sort_order"]),
        "MOVING_MIN_MANA": f'{moving["min_mana_pct"]:.2f}f',
        "MOVING_MAX_MANA": f'{moving["max_mana_pct"]:.2f}f',
        "MOVING_BUCKET": str(moving["priority_bucket"]),
        "MOVING_SORT": str(moving["sort_order"]),
    }
    for key, value in substitutions.items():
        program = program.replace(key, value)
    source.write_text(program, encoding="utf-8")
    subprocess.run(
        [
            "c++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
            "-I", str(ROOT / "src/server/game"),
            "-I", str(ROOT / "src/server/game/Spells/Auras"),
            "-I", str(ROOT / "src/common"),
            "-I", str(ROOT / "src/common/Utilities"),
            "-I", str(ROOT / "src/server/game/Entities/Object"),
            str(source), "-o", str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)

    assert "BotCastWhileMoving::RejectMovingCandidate" in resolver_source
    assert "manaPct > candidate.Profile.MaxManaPct" in resolver_source
    assert "candidate.Profile.RequiresMoving && !bot->isMoving()" in resolver_source
