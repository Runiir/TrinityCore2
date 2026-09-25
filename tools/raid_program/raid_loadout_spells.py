"""Spellbook of a two-spec loadout character before login.

A native dual-spec character knows the active group's talents, its primary
tree spells and everything those teach (SPELL_EFFECT_LEARN_SPELL), plus every
trainable class spell. Player::ActivateSpec removes the other group's talent
and tree spells (and their taught spells) and learns them only when that
group becomes active. The provisioned spellbook follows the same rule:

    inactive_only = LEARN closure(inactive talents + inactive tree spells)
                  + inactive spec's talent-gated action-profile spells
                  - LEARN closure(active talents + active tree spells)
                  - the active spec's single-spec spellbook
    known         = active single-spec spellbook
                  + every group's baseline action-profile spells
                  - inactive_only
                  + the dual-spec switch spells 63644/63645

The native baseline, which is never removed, is the LEARN closure of
- every SkillLineAbility spell with AcquireMethod 1 or 2 (AutomaticSkillRank,
  AutomaticCharLevel) whose RaceMask and ClassMask match the character: the
  core learns these at login through LearnDefaultSkills ->
  LearnSkillRewardedSpells (Player.cpp:17160, 23284-23300, 23416-23460);
- every class-trainer spell whose prerequisite ability is itself baseline.
  Class trainers are the trainer IDs whose taught spells belong to the class
  (SkillLineAbility ClassMask), not a subname: Death Knight trainers have none.

An action-profile spell is talent-gated when it is outside that baseline and is
not a class-wide or proficiency spell; e.g. Sunfire 93402 exists only through
the Balance talent 93401 (spell_druid.cpp:116, 231-234).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from tools.bot_ml.build_validation_provisioning import (
    DEFAULT_ACTION_PROFILES,
    NATIVE_SELF_SETUP_SPELL_IDS,
    bot_known_spell_ids,
    bot_primary_tree_spell_ids,
    bot_spell_ids,
    load_wdbc_values,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TRAINERS = REPO_ROOT / "dataset/world_knowledge/trainers.jsonl"
SPELL_EFFECT_FMT = "nifiiiffiiiiiifiifiiiiiiiix"
SPELL_EFFECT_LEARN_SPELL = 36
SPELL_EFFECT_FIELD = 1
TRIGGER_SPELL_FIELD = 21
SPELL_ID_FIELD = 24
# Activating Secondary Spec / Activating Primary Spec (SPELL_EFFECT_TALENT_SPEC_SELECT),
# taught natively by 63680 when a character buys dual specialization.
DUAL_SPEC_SWITCH_SPELL_IDS = (63644, 63645)
CLASS_TRAINER_TYPE = 0
MAX_TRAINER_LEVEL = 85
# SkillLineAbility.dbc (TrinityCore SkillLineAbilityfmt "niiiixxiiiiiii" plus the two skipped fields).
SKILL_LINE_ABILITY_FMT = "n" + "i" * 13
SKILL_SPELL_FIELD, SKILL_RACE_MASK_FIELD, SKILL_CLASS_MASK_FIELD, SKILL_ACQUIRE_FIELD = 2, 3, 4, 9
AUTO_ACQUIRE_METHODS = (1, 2)  # SkillLineAbilityAcquireMethod::AutomaticSkillRank / AutomaticCharLevel
# A trainer ID belongs to a class when at least this share of its class-masked spells is that class's.
TRAINER_CLASS_SHARE = 0.8
_LEARN_CACHE: dict[Path, dict[int, list[int]]] = {}
_SKILL_CACHE: dict[Path, list[tuple[int, int, int, int]]] = {}
_TRAINER_CACHE: dict[tuple[Path, Path], dict[str, Any]] = {}
_BASELINE_CACHE: dict[tuple[Path, Path, int, int], frozenset[int]] = {}


class LoadoutSpellError(ValueError):
    pass


def spell_learn_map(dbc_dir: Path) -> dict[int, list[int]]:
    """spell -> spells it teaches through SPELL_EFFECT_LEARN_SPELL (SpellEffect.dbc)."""
    dbc_dir = Path(dbc_dir).resolve()
    cached = _LEARN_CACHE.get(dbc_dir)
    if cached is not None:
        return cached
    mapping: dict[int, list[int]] = {}
    for row in load_wdbc_values(dbc_dir / "SpellEffect.dbc", SPELL_EFFECT_FMT):
        if int(row[SPELL_EFFECT_FIELD]) == SPELL_EFFECT_LEARN_SPELL and int(row[TRIGGER_SPELL_FIELD]) > 0:
            mapping.setdefault(int(row[SPELL_ID_FIELD]), []).append(int(row[TRIGGER_SPELL_FIELD]))
    _LEARN_CACHE[dbc_dir] = mapping
    return mapping


def learn_closure(spells: Iterable[int], learn_map: dict[int, list[int]]) -> set[int]:
    result: set[int] = set()
    pending = [int(spell) for spell in spells]
    while pending:
        spell = pending.pop()
        if spell in result:
            continue
        result.add(spell)
        pending.extend(learn_map.get(spell, ()))
    return result


def skill_line_abilities(dbc_dir: Path) -> list[tuple[int, int, int, int]]:
    """(spell, race mask, class mask, acquire method) rows of SkillLineAbility.dbc."""
    dbc_dir = Path(dbc_dir).resolve()
    cached = _SKILL_CACHE.get(dbc_dir)
    if cached is None:
        cached = [(int(row[SKILL_SPELL_FIELD]), int(row[SKILL_RACE_MASK_FIELD]), int(row[SKILL_CLASS_MASK_FIELD]),
                   int(row[SKILL_ACQUIRE_FIELD]))
                  for row in load_wdbc_values(dbc_dir / "SkillLineAbility.dbc", SKILL_LINE_ABILITY_FMT)]
        _SKILL_CACHE[dbc_dir] = cached
    return cached


def auto_learned_spells(dbc_dir: Path, race: int, class_id: int) -> set[int]:
    """Spells Player::LearnSkillRewardedSpells teaches this race/class at login."""
    race_mask, class_mask = 1 << (int(race) - 1), 1 << (int(class_id) - 1)
    return {spell for spell, races, classes, acquire in skill_line_abilities(dbc_dir)
            if acquire in AUTO_ACQUIRE_METHODS and (not races or races & race_mask)
            and (not classes or classes & class_mask)}


def trainer_classes(trainers_path: Path, dbc_dir: Path) -> dict[str, Any]:
    """Trainer ID -> class, inferred from the ClassMask of the spells each trainer ID teaches."""
    key = (Path(trainers_path).resolve(), Path(dbc_dir).resolve())
    cached = _TRAINER_CACHE.get(key)
    if cached is not None:
        return cached
    class_masks: dict[int, set[int]] = {}
    for spell, _races, classes, _acquire in skill_line_abilities(dbc_dir):
        if classes:
            class_masks.setdefault(spell, set()).add(classes)
    offers: dict[int, dict[int, set[int]]] = {}
    if Path(trainers_path).is_file():
        with Path(trainers_path).open(encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                for spell in row.get("trainer_spells") or []:
                    if (int(spell.get("trainer_type", -1)) != CLASS_TRAINER_TYPE
                            or int(spell.get("req_level") or 0) > MAX_TRAINER_LEVEL):
                        continue
                    for trainer_id in row.get("trainer_ids") or []:
                        offers.setdefault(int(trainer_id), {}).setdefault(int(spell["spell_id"]), set()).add(
                            int(spell.get("req_ability1") or 0))
    classes_by_trainer: dict[int, int] = {}
    for trainer_id, spells in offers.items():
        votes: dict[int, int] = {}
        voters = 0
        for spell in spells:
            masks = class_masks.get(spell)
            if not masks:
                continue
            voters += 1
            for class_id in {bit + 1 for mask in masks for bit in range(32) if mask & (1 << bit)}:
                votes[class_id] = votes.get(class_id, 0) + 1
        if votes:
            class_id, count = max(votes.items(), key=lambda item: (item[1], -item[0]))
            if count >= TRAINER_CLASS_SHARE * voters:
                classes_by_trainer[trainer_id] = class_id
    result = {"offers": offers, "classes": classes_by_trainer}
    _TRAINER_CACHE[key] = result
    return result


def native_baseline(class_id: int, race: int, dbc_dir: Path, learn_map: dict[int, list[int]],
                    trainers_path: Path = DEFAULT_TRAINERS) -> frozenset[int]:
    """Spells a level-85 character of this race/class knows whatever its talent groups hold."""
    key = (Path(trainers_path).resolve(), Path(dbc_dir).resolve(), int(class_id), int(race))
    cached = _BASELINE_CACHE.get(key)
    if cached is not None:
        return cached
    trainers = trainer_classes(trainers_path, dbc_dir)
    class_trainers = [trainer for trainer, owner in trainers["classes"].items() if owner == int(class_id)]
    if not class_trainers:
        raise LoadoutSpellError(f"class_trainer_baseline_missing:{class_id}:{trainers_path}")
    offers: dict[int, set[int]] = {}
    for trainer in class_trainers:
        for spell, requirements in trainers["offers"][trainer].items():
            offers.setdefault(spell, set()).update(requirements)
    known = learn_closure(auto_learned_spells(dbc_dir, race, class_id), learn_map)
    # A trainer spell is baseline when some offer needs no ability or needs an
    # ability that is itself baseline (e.g. Maul requires Bear Form); an offer
    # that requires a talent stays talent-gated.
    changed = True
    while changed:
        changed = False
        for spell, requirements in offers.items():
            if spell not in known and any(not req or req in known for req in requirements):
                known |= learn_closure([spell], learn_map)
                changed = True
    result = frozenset(known)
    _BASELINE_CACHE[key] = result
    return result


def trainers_sha256(trainers_path: Path = DEFAULT_TRAINERS) -> str | None:
    path = Path(trainers_path)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _view(bot: dict[str, Any], group: dict[str, Any]) -> dict[str, Any]:
    return {"class": bot["class"], "class_spec": group["class_spec"], "spells": bot.get("spells", []),
            "primary_talent_tree_id": group["primary_talent_tree_id"], "talents": group["talents"]}


def specialization_closure(group: dict[str, Any], learn_map: dict[int, list[int]]) -> set[int]:
    seeds = {int(talent["spell_id"]) for talent in group["talents"]} | set(bot_primary_tree_spell_ids(group))
    return learn_closure(seeds, learn_map)


def talent_gated_profile_spells(class_id: int, class_spec: str, baseline: frozenset[int],
                                action_profiles: dict[str, Any]) -> set[int]:
    spec_spells = {int(spell) for spell in action_profiles.get("action_profile_spells_by_spec", {}).get(class_spec, [])}
    class_wide = {int(spell) for spell in action_profiles["action_profile_spells_by_class"].get(int(class_id), [])}
    proficiency = {int(spell) for spell in action_profiles["proficiency_spells_by_class"].get(int(class_id), [])}
    return spec_spells - set(baseline) - class_wide - proficiency


def loadout_known_spells(bot: dict[str, Any], dbc_dir: Path, action_profiles: dict[str, Any] | None = None,
                         trainers_path: Path = DEFAULT_TRAINERS) -> dict[str, list[int]]:
    action_profiles = action_profiles or DEFAULT_ACTION_PROFILES
    loadout = bot["loadout"]
    groups = loadout["groups"]
    active = groups[int(loadout["active_talent_group"])]
    learn_map = spell_learn_map(dbc_dir)
    single_active = set(bot_known_spell_ids(_view(bot, active), action_profiles))
    inactive = [group for group in groups
                if group is not active and group.get("mirrors_talent_group") is None
                and group["class_spec"] != active["class_spec"]]
    inactive_only: set[int] = set()
    if inactive:
        baseline = native_baseline(int(bot["class"]), int(bot["race"]), dbc_dir, learn_map, trainers_path)
        for group in inactive:
            inactive_only |= specialization_closure(group, learn_map)
            inactive_only |= talent_gated_profile_spells(int(bot["class"]), str(group["class_spec"]),
                                                        baseline, action_profiles)
        inactive_only -= specialization_closure(active, learn_map) | single_active | baseline
    known = set(single_active)
    for group in groups:
        known.update(bot_spell_ids(_view(bot, group), action_profiles))
        known.update(NATIVE_SELF_SETUP_SPELL_IDS.get(str(group["class_spec"]), ()))
    known -= inactive_only
    if int(loadout.get("talent_groups_count") or 0) > 1:
        known.update(DUAL_SPEC_SWITCH_SPELL_IDS)
    missing_active = sorted(single_active - known)
    if missing_active:
        raise LoadoutSpellError(f"active_single_spec_spells_dropped:{bot.get('name')}:{missing_active}")
    return {"known_spell_ids": sorted(known), "inactive_only_spell_ids": sorted(inactive_only),
            "dual_spec_switch_spell_ids": sorted(DUAL_SPEC_SWITCH_SPELL_IDS)
            if int(loadout.get("talent_groups_count") or 0) > 1 else []}
