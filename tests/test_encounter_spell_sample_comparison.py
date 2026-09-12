import pytest
from tools.raid_program.compare_encounter_spell_samples import compare


def inputs():
    # Pinned 59185 ordinary Spit effect and two public fight-10 observations.
    client = {'rows': {'SpellEffect': [dict(SpellID='78359', EffectIndex='0',
        DifficultyID='0', ID='77915', Effect='2', EffectBonusCoefficient='0',
        EffectBasePoints='30624', EffectDieSides='8751')]}}
    observations = dict(report='xAhkN2y9YP3KRmnJ', fight=10, mode='10N',
        columns=['spell_id', 'displayed_damage', 'displayed_absorb', 'wcl_unmitigated_estimate'],
        samples=[[78359, 30221, 1590, 31811], [78359, 37363, 1966, 39329]])
    return client, observations


def test_compares_explicit_u_without_confusing_absorption_with_low_base_damage():
    client, observations = inputs()
    result = compare(client, observations, 0)
    spell = result['spells'][0]
    assert spell['outside_client_roll'] == 0
    assert spell['observed_min'] == 31811
    assert result['conclusion'] == 'sample_compatibility_only'
    # Substituting the Tantrum variant's lower base would reject both samples.
    client['rows']['SpellEffect'][0].update(EffectBasePoints='24499', EffectDieSides='7001')
    assert compare(client, observations, 0)['spells'][0]['outside_client_roll'] == 2


def test_missing_u_is_not_reconstructed_from_health_loss_or_gear():
    client, observations = inputs()
    for sample in observations['samples']:
        sample[-1] = None
    with pytest.raises(ValueError, match='no explicit WCL'):
        compare(client, observations, 0)


def test_missing_difficulty_does_not_silently_fall_back():
    client, observations = inputs()
    with pytest.raises(ValueError, match='explicit difficulty'):
        compare(client, observations, 5)
