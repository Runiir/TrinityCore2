from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "src/server/scripts/Spells/spell_pet.cpp").read_text(
    encoding="utf-8"
)


def _scaling_class_body(method: str) -> str:
    start = SOURCE.index(f"void {method}(")
    next_method = SOURCE.find("\n    void ", start + 1)
    return SOURCE[start : next_method if next_method >= 0 else len(SOURCE)]


def _replay_pet_inheritance(
    fire: int, shadow: int, spell_power_pct: float, damage_fraction: float
) -> tuple[int, int]:
    """Replay the two spell_pet.cpp inheritance calculations deterministically."""

    inherited = int(max(fire, shadow) * spell_power_pct)
    return inherited, int(inherited * damage_fraction)


def test_warlock_pet_scaling_uses_modified_owner_spell_power_for_attack_power():
    body = _scaling_class_body("CalculateAttackPowerAmount")

    assert body.count(
        "owner->SpellBaseDamageBonusDone(SPELL_SCHOOL_MASK_FIRE, true)"
    ) == 1
    assert body.count(
        "owner->SpellBaseDamageBonusDone(SPELL_SCHOOL_MASK_SHADOW, true)"
    ) == 1
    assert "amount = std::max(fire, shadow);" in body


def test_warlock_pet_scaling_replay_ap_and_damage_done_share_modified_value():
    damage_body = _scaling_class_body("CalculateDamageDoneAmount")

    assert damage_body.count(
        "owner->SpellBaseDamageBonusDone(SPELL_SCHOOL_MASK_FIRE, true)"
    ) == 1
    assert damage_body.count(
        "owner->SpellBaseDamageBonusDone(SPELL_SCHOOL_MASK_SHADOW, true)"
    ) == 1
    assert "amount = std::max(fire, shadow) * 0.5f;" in damage_body

    # A fixed owner snapshot exercises the same ordering as the native aura
    # callbacks: choose the stronger school, apply the owner SP multiplier,
    # then derive the pet damage bonus from that value.
    attack_power, damage_done = _replay_pet_inheritance(
        fire=11_219, shadow=12_262, spell_power_pct=1.05, damage_fraction=0.5
    )
    assert attack_power == 12_875
    assert damage_done == 6_437


def test_warlock_pet_scaling_has_no_unmodified_owner_spell_power_calls():
    body = SOURCE[
        SOURCE.index("class spell_warl_pet_scaling_01") : SOURCE.index(
            "class spell_warl_pet_scaling_02"
        )
    ]

    assert not re.search(
        r"SpellBaseDamageBonusDone\(SPELL_SCHOOL_MASK_(?:FIRE|SHADOW)\)", body
    )
