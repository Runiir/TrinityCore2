#ifndef TRINITY_BOT_CALIBRATION_PRE_SCORE_STATE_JSON_H
#define TRINITY_BOT_CALIBRATION_PRE_SCORE_STATE_JSON_H
#include <sstream>
#include <string>

// All source classifications are fixed literals assigned by the aura classifier.
template<class Metrics>
std::string BotCalibrationPreScoreStateJson(Metrics const* metrics)
{
    std::ostringstream json;
    json
             << "{\"schema\":\"phase8_pre_score_state_observation_v1\""
             << ",\"observed_at_ms\":"
             << (metrics ? metrics->PreScoreStateObservedAtMs : 0)
             << ",\"observed_before_scoring\":"
             << (metrics && metrics->PreScoreStateObservedAtMs
                    && metrics->WindowStartedMs
                    && metrics->PreScoreStateObservedAtMs
                        <= metrics->WindowStartedMs ? "true" : "false")
             << ",\"persistent_setup_ready\":"
             << (metrics && metrics->PreScorePersistentSetupReady ? "true" : "false")
             << ",\"reference_buffs_ready\":"
             << (metrics && metrics->PreScoreReferenceBuffsReady ? "true" : "false")
             << ",\"reference_target_debuffs_ready\":"
             << (metrics && metrics->PreScoreReferenceTargetDebuffsReady ? "true" : "false")
             << ",\"heroism_ready\":"
             << (metrics && metrics->PreScoreHeroismReady ? "true" : "false")
             << ",\"temporal_external_auras_absent\":"
             << (metrics && metrics->PreScoreTemporalExternalsAbsent ? "true" : "false")
             << ",\"external_bleed_auras_absent\":"
             << (metrics && metrics->PreScoreExternalBleedAbsent ? "true" : "false")
             << ",\"self_provided_player_auras_compatible\":"
             << (metrics && metrics->PreScoreSelfProvidedPlayerAurasCompatible ? "true" : "false")
             << ",\"self_provided_target_auras_compatible\":"
             << (metrics && metrics->PreScoreSelfProvidedTargetAurasCompatible ? "true" : "false")
             << ",\"self_provided_player_aura_spell_id\":" << (metrics ? metrics->PreScoreSelfProvidedPlayerAuraSpellId : 0)
             << ",\"self_provided_player_aura_source\":\"" << (metrics ? metrics->PreScoreSelfProvidedPlayerAuraSource : "unobserved") << "\""
             << ",\"self_provided_target_aura_spell_id\":" << (metrics ? metrics->PreScoreSelfProvidedTargetAuraSpellId : 0)
             << ",\"self_provided_target_aura_source\":\"" << (metrics ? metrics->PreScoreSelfProvidedTargetAuraSource : "unobserved") << "\""
             << ",\"last_potion_item_id\":"
             << (metrics ? metrics->PreScoreLastPotionItemId : 0)
             << ",\"no_active_cast\":"
             << (metrics && metrics->PreScoreNoActiveCast ? "true" : "false")
             << ",\"no_combat\":"
             << (metrics && metrics->PreScoreNoCombat ? "true" : "false")
             << ",\"global_cooldown_clear\":"
             << (metrics && metrics->PreScoreGlobalCooldownClear ? "true" : "false")
             << ",\"cooldown_reset_applied\":"
             << (metrics && metrics->PreScoreCooldownResetApplied ? "true" : "false")
             << ",\"warmup_profile_actions_suppressed\":"
             << (metrics && metrics->WarmupProfileActionsSuppressed ? "true" : "false") << '}'
             ;
    return json.str();
}
#endif
