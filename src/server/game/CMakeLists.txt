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
  ${CMAKE_CURRENT_SOURCE_DIR}/Bots/BotWorldPopulationMgrRecovery.cpp
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
