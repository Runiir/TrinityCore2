#ifndef TRINITY_SPELL_MAGE_SHARED_H
#define TRINITY_SPELL_MAGE_SHARED_H

namespace Spells::Mage
{
enum MageSpells
{
    SPELL_MAGE_ARCANE_POTENCY_RANK_1             = 31571,
    SPELL_MAGE_ARCANE_POTENCY_RANK_2             = 31572,
    SPELL_MAGE_ARCANE_POTENCY_TRIGGER_RANK_1     = 57529,
    SPELL_MAGE_ARCANE_POTENCY_TRIGGER_RANK_2     = 57531,
    SPELL_MAGE_ARCANE_BLAST                      = 30451,
    SPELL_MAGE_ARCANE_MISSILES                   = 5143,
    SPELL_MAGE_ARCANE_MISSILES_AURASTATE         = 79808,
    SPELL_MAGE_BLAZING_SPEED                     = 31643,
    SPELL_MAGE_BRAIN_FREEZE_R1                   = 44546,
    SPELL_MAGE_BURNOUT                           = 29077,
    SPELL_MAGE_COLD_SNAP                         = 11958,
    SPELL_MAGE_COMBUSTION_DAMAGE                 = 83853,
    SPELL_MAGE_DEEP_FREEZE_DAMAGE                = 71757,
    SPELL_MAGE_EARLY_FROST_R1                    = 83049,
    SPELL_MAGE_EARLY_FROST_R2                    = 83050,
    SPELL_MAGE_EARLY_FROST_TRIGGERED_R1          = 83162,
    SPELL_MAGE_EARLY_FROST_TRIGGERED_R2          = 83239,
    SPELL_MAGE_EARLY_FROST_VISUAL                = 94315,
    SPELL_MAGE_FIREBALL                          = 133,
    SPELL_MAGE_FIRE_BLAST                        = 2136,
    SPELL_MAGE_FROST_NOVA                        = 122,
    SPELL_MAGE_FLAME_ORB_DUMMY                   = 82731,
    SPELL_MAGE_FLAME_ORB_SUMMON                  = 84765,
    SPELL_MAGE_FLAME_ORB_AOE                     = 82734,
    SPELL_MAGE_FLAME_ORB_BEAM_DUMMY              = 86719,
    SPELL_MAGE_FLAME_ORB_DAMAGE                  = 82739,
    SPELL_MAGE_FLAME_ORB_SELF_SNARE              = 82736,
    SPELL_MAGE_FROSTFIRE_BOLT                    = 44614,
    SPELL_MAGE_FROSTFIRE_ORB_DUMMY               = 92283,
    SPELL_MAGE_FROSTFIRE_ORB_SUMMON              = 84714,
    SPELL_MAGE_FROSTFIRE_ORB_AOE                 = 84718,
    SPELL_MAGE_FROSTFIRE_ORB_DAMAGE_R1           = 95969,
    SPELL_MAGE_FROSTFIRE_ORB_DAMAGE_R2           = 84721,
    SPELL_MAGE_FROSTFIRE_ORB_RANK_R2             = 84727,
    SPELL_MAGE_FROSTFIRE_BOLT_CHILL_EFFECT       = 44614,
    SPELL_MAGE_HOT_STREAK                        = 44445,
    SPELL_MAGE_HOT_STREAK_TRIGGERED              = 48108,
    SPELL_MAGE_HYPOTHERMIA                       = 41425,
    SPELL_MAGE_IMPROVED_HOT_STREAK               = 44446,
    SPELL_MAGE_IMPROVED_POLYMORPH_RANK_1         = 11210,
    SPELL_MAGE_IMPROVED_POLYMORPH_STUN_RANK_1    = 83046,
    SPELL_MAGE_IMPROVED_POLYMORPH_MARKER         = 87515,
    SPELL_MAGE_INCANTERS_ABSORBTION_TRIGGERED    = 44413,
    SPELL_MAGE_INCANTERS_ABSORBTION_KNOCKBACK    = 86261,
    SPELL_MAGE_IGNITE                            = 12654,
    SPELL_MAGE_LIVING_BOMB                       = 44457,
    SPELL_MAGE_MASTER_OF_ELEMENTS_ENERGIZE       = 29077,
    SPELL_MAGE_MIRROR_IMAGE_TRIGGERED_FIRE       = 88092,
    SPELL_MAGE_MIRROR_IMAGE_TRIGGERED_ARCANE     = 88091,
    SPELL_MAGE_MIRROR_IMAGE_TRIGGERED_FROST      = 58832,
    SPELL_MAGE_PERMAFROST_REDUCE_HEAL            = 68391,
    SPELL_MAGE_PERMAFROST_HEAL                   = 91394,
    SPELL_MAGE_PYROBLAST                         = 11366,
    SPELL_MAGE_PYROBLAST_HOT_STREAK              = 92315,
    SPELL_MAGE_PYROMANIAC_TRIGGERED              = 83582,
    SPELL_MAGE_SCORCH                            = 2948,
    SPELL_MAGE_SLOW                              = 31589,
    SPELL_MAGE_T12_4P_BONUS                      = 99064,
    SPELL_MAGE_GLYPH_OF_ETERNAL_WATER            = 70937,
    SPELL_MAGE_SHATTERED_BARRIER                 = 55080,
    SPELL_MAGE_SUMMON_WATER_ELEMENTAL_PERMANENT  = 70908,
    SPELL_MAGE_SUMMON_WATER_ELEMENTAL_TEMPORARY  = 70907,
    SPELL_MAGE_GLYPH_OF_BLAST_WAVE               = 62126,

    SPELL_MAGE_FLAMESTRIKE                       = 2120,

    SPELL_MAGE_CHILLED_R1                        = 12484,
    SPELL_MAGE_CHILLED_R2                        = 12485,

    SPELL_MAGE_CONE_OF_COLD_AURA_R1              = 11190,
    SPELL_MAGE_CONE_OF_COLD_AURA_R2              = 12489,
    SPELL_MAGE_CONE_OF_COLD_TRIGGER_R1           = 83301,
    SPELL_MAGE_CONE_OF_COLD_TRIGGER_R2           = 83302,

    SPELL_MAGE_SHATTERED_BARRIER_R1              = 44745,
    SPELL_MAGE_SHATTERED_BARRIER_R2              = 54787,
    SPELL_MAGE_SHATTERED_BARRIER_FREEZE_R1       = 55080,
    SPELL_MAGE_SHATTERED_BARRIER_FREEZE_R2       = 83073,

    SPELL_MAGE_IMPROVED_MANA_GEM_TRIGGERED       = 83098,

    SPELL_MAGE_RING_OF_FROST_SUMMON              = 82676,
    SPELL_MAGE_RING_OF_FROST_FREEZE              = 82691,
    SPELL_MAGE_RING_OF_FROST_DUMMY               = 91264,

    SPELL_MAGE_FINGERS_OF_FROST                  = 44544,
    SPELL_MAGE_TEMPORAL_DISPLACEMENT             = 80354,
};

enum MageIcons
{
    ICON_MAGE_SHATTER                            = 976,
    ICON_MAGE_IMPROVED_CONE_OF_COLD              = 35,
    ICON_MAGE_IMPROVED_FLAMESTRIKE               = 37,
    ICON_MAGE_IMPROVED_FREEZE                    = 94,
    ICON_MAGE_INCANTERS_ABSORPTION               = 2941,
    ICON_MAGE_IMPROVED_MANA_GEM                  = 1036,
    ICON_MAGE_EARLY_FROST_SKILL                  = 189,
    ICON_MAGE_EARLY_FROST                        = 2114,
    ICON_MAGE_GLYPH_OF_ICE_BLOCK                 = 14,
    ICON_MAGE_GLYPH_OF_ICY_VEINS                 = 2162,
    ICON_MAGE_GLYPH_OF_MIRROR_IMAGE              = 331,
    ICON_MAGE_GLYPH_OF_POLYMORPH                 = 82,
    ICON_MAGE_LIVING_BOMB                        = 3000,
    ICON_MAGE_GLYPH_OF_FROSTFIRE                 = 2946,
    ICON_MAGE_HOT_STREAK                         = 2999

};

enum MiscSpells
{
    SPELL_HUNTER_INSANITY                        = 95809,
    SPELL_PRIEST_SHADOW_WORD_DEATH               = 32409,
    SPELL_SHAMAN_EXHAUSTION                      = 57723,
    SPELL_SHAMAN_SATED                           = 57724
};

enum MageSpellIcons
{
    SPELL_ICON_MAGE_SHATTERED_BARRIER = 2945
};

void RegisterMageScript_blast_wave();
void RegisterMageScript_blazing_speed();
void RegisterMageScript_combustion();
void RegisterMageScript_dragon_breath();
void RegisterMageScript_hot_streak();
void RegisterMageScript_ignite();
void RegisterMageScript_ignite_periodic();
void RegisterMageScript_impact();
void RegisterMageScript_impact_triggered();
void RegisterMageScript_improved_hot_streak();
void RegisterMageScript_living_bomb();
void RegisterMageScript_pyromaniac();
void RegisterMageScript_blizzard();
void RegisterMageScript_cold_snap();
void RegisterMageScript_cone_of_cold();
void RegisterMageScript_deep_freeze();
void RegisterMageScript_early_frost();
void RegisterMageScript_frostbolt();
void RegisterMageScript_frostfire_bolt();
void RegisterMageScript_ice_barrier();
void RegisterMageScript_ice_block();
void RegisterMageScript_icy_veins();
void RegisterMageScript_permafrost();
void RegisterMageScript_ring_of_frost();
void RegisterMageScript_ring_of_frost_freeze();
void RegisterMageScript_water_elemental_freeze();
}
#endif
