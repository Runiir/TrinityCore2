"""Retired creation oracle for the current Cataclysm stat/rating mapping."""
import struct
SUPPORTED={*range(2,11),14,15,17,18,19,23,25}


def creation(native,index,unit,active):
    def floating(name):return struct.unpack('<f',struct.pack('<I',native.get(index[name],0)))[0]
    for modern,name in [('ModHaste','PLAYER_FIELD_MOD_HASTE'),('ModRangedHaste','PLAYER_FIELD_MOD_RANGED_HASTE'),
        ('ModHasteRegen','PLAYER_FIELD_MOD_HASTE_REGEN')]:
        unit[modern]=floating(name) if index[name] in native else 1.0
    for modern,name in [('MainhandExpertise','PLAYER_EXPERTISE'),('OffhandExpertise','PLAYER_OFFHAND_EXPERTISE')]:
        active[modern]=float(native.get(index[name],0))
    active['ShieldBlock']=native.get(index['PLAYER_SHIELD_BLOCK'],0)
    for modern,name in [('BlockPercentage','PLAYER_BLOCK_PERCENTAGE'),('DodgePercentage','PLAYER_DODGE_PERCENTAGE'),
        ('ParryPercentage','PLAYER_PARRY_PERCENTAGE'),('Mastery','PLAYER_MASTERY')]:active[modern]=floating(name)
    active['CombatRatings']=[native.get(index['PLAYER_FIELD_COMBAT_RATING_1']+i,0) if i in SUPPORTED else 0 for i in range(32)]
