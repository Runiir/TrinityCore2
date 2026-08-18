# This file is part of the TrinityCore Project. See AUTHORS file for Copyright information
#
# This file is free software; as a special exception the author gives
# unlimited permission to copy and/or distribute it, with or without
# modifications, as long as this notice is preserved.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY, to the extent permitted by law; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

CollectSourceFiles(
  ${CMAKE_CURRENT_SOURCE_DIR}
  PRIVATE_SOURCES
  # Exclude
  ${CMAKE_CURRENT_SOURCE_DIR}/PrecompiledHeaders)

list(APPEND PRIVATE_SOURCES
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotActionExecutor.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotClassSpecActionProfile.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotCombatActionCatalog.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotController.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotDatasetEvent.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotEncounterMechanicCatalog.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotExperimentCoordinator.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotExperienceLearningPolicy.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotLongTermProgressionBrain.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotMgr.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotProgressionGoalPolicy.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotRoleSaturationPolicy.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotTelemetryBuffer.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotTelemetryPolicy.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotTypes.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrCohort.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrAffliction.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrQuestSelection.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrQuestRouting.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrQuestActions.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrSpawnMemory.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrMovement.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrCombatMovement.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrCombatDiagnostics.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrCombatLog.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrDecisionTrace.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrDiagnosis.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrGearMemory.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrProgressionTelemetry.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrTelemetryPolicy.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrEventRecording.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrStateJson.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrRaidRuntime.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrEncounterJson.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrPersistentSetup.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrCombatExecution.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrCombatResolver.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrCombatRes.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrConfig.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrValidationLifecycle.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrCalibrationPopulation.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrCalibrationGroup.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrCalibrationDamage.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrCalibrationReset.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrCalibrationCompletion.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrValidationAdmission.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrLifecycle.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrEncounterBlackboard.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrRecordingWindow.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrPolicyDeployment.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrValidationProfile.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrUpdate.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrRoster.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrValidationRecoveryGate.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrGearIdentity.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrRaidPlanning.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrQuestObjective.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrDungeonTargeting.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrCombatSupport.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrCombatSpell.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrCombatNotifications.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrPopulation.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrCalibrationReference.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrCalibrationHealer.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrCalibrationBot.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrCalibrationBotJson.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrCalibrationReferenceJson.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrCalibrationSummaryJson.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrUpdateDeath.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrNativeAction.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrValidationCohortRuntime.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrValidationAuthority.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrValidationGroupHeal.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrValidationPatrolPull.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrValidationFeralPickup.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrValidationSwarmApproach.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrValidationTerminal.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrValidationLivePack.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrValidationOutcomes.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrBossTargeting.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrValidationNoProgress.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrBossDispatch.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrBossMechanics.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrBossMechanicsSupport.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrValidationTargeting.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrDungeonRoute.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrValidationFocus.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrCalibrationControl.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrValidationActivation.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrValidationInterrupt.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrValidationHazards.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrValidationRouteRuntime.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrValidationRouteManifest.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrPolicyModel.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrReplay.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrRecovery.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrSemantic.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrStatus.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrRuntimeProfiles.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgr.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/HealerBotPolicy.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/HolyPaladinResolver.cpp)

if(USE_COREPCH)
  set(PRIVATE_PCH_HEADER PrecompiledHeaders/gamePCH.h)
endif()

GroupSources(${CMAKE_CURRENT_SOURCE_DIR})

add_definitions(-DTRINITY_API_EXPORT_GAME)

CollectIncludeDirectories(
  ${CMAKE_CURRENT_SOURCE_DIR}
  PUBLIC_INCLUDES
  # Exclude
  ${CMAKE_CURRENT_SOURCE_DIR}/PrecompiledHeaders)

# Provide an interface target for the game project to allow
# dependent projects to build meanwhile.
add_library(game-interface INTERFACE)

target_include_directories(game-interface
  INTERFACE
    ${PUBLIC_INCLUDES})

target_link_libraries(game-interface
  INTERFACE
    shared
    Detour)

add_library(game
  ${PRIVATE_SOURCES})

target_include_directories(game
  PRIVATE
    ${CMAKE_CURRENT_BINARY_DIR})

target_link_libraries(game
  PRIVATE
    trinity-core-interface
    efsw
    rapidjson
  PUBLIC
    game-interface)

set_target_properties(game
    PROPERTIES
      FOLDER
        "server")

if(UNITY_BUILDS)
  set_target_properties(game
      PROPERTIES UNITY_BUILD ON)
  set_target_properties(game
      PROPERTIES
        UNITY_BUILD_MODE BATCH
        UNITY_BUILD_BATCH_SIZE 8)
endif()

if(BUILD_SHARED_LIBS)
  if(UNIX)
    install(TARGETS game
      LIBRARY
        DESTINATION lib)
  elseif(WIN32)
    install(TARGETS game
      RUNTIME
        DESTINATION "${CMAKE_INSTALL_PREFIX}")
  endif()
endif()

# Generate precompiled header
if(USE_COREPCH)
  add_cxx_pch(game ${PRIVATE_PCH_HEADER})
endif()
