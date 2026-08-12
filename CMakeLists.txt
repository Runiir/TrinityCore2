# This file is part of the TrinityCore Project. See AUTHORS file for Copyright information
#
# This file is free software; as a special exception the author gives
# unlimited permission to copy and/or distribute it, with or without
# modifications, as long as this notice is preserved.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY, to the extent permitted by law; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

cmake_minimum_required(VERSION 3.18)

# add this options before PROJECT keyword
set(CMAKE_DISABLE_SOURCE_CHANGES ON)
set(CMAKE_DISABLE_IN_SOURCE_BUILD ON)

# Set projectname (must be done AFTER setting configurationtypes)
project(TrinityCore)

# Raid-program builds are admitted by tools/raid_program/queued_build.py.  When
# its lease environment is present, cap compilation and serialize link commands
# mechanically for both Ninja job pools and Make/Ninja rule launches.
if(DEFINED ENV{TRINITY_RAID_BUILD_COORDINATED} AND "$ENV{TRINITY_RAID_BUILD_COORDINATED}" STREQUAL "1")
  foreach(REQUIRED_RAID_BUILD_ENV
      TRINITY_RAID_BUILD_TICKET
      TRINITY_RAID_BUILD_COMPILER_JOBS
      TRINITY_RAID_BUILD_LINKER_JOBS
      TRINITY_RAID_BUILD_LINK_LOCK)
    if(NOT DEFINED ENV{${REQUIRED_RAID_BUILD_ENV}} OR "$ENV{${REQUIRED_RAID_BUILD_ENV}}" STREQUAL "")
      message(FATAL_ERROR "Coordinated raid build is missing ${REQUIRED_RAID_BUILD_ENV}")
    endif()
  endforeach()

  set_property(GLOBAL PROPERTY JOB_POOLS
    "trinity_raid_compile_pool=$ENV{TRINITY_RAID_BUILD_COMPILER_JOBS}"
    "trinity_raid_link_pool=$ENV{TRINITY_RAID_BUILD_LINKER_JOBS}")
  set(CMAKE_JOB_POOL_COMPILE trinity_raid_compile_pool)
  set(CMAKE_JOB_POOL_LINK trinity_raid_link_pool)
  find_program(TRINITY_RAID_FLOCK_EXECUTABLE flock REQUIRED)
  set_property(GLOBAL PROPERTY RULE_LAUNCH_LINK
    "${TRINITY_RAID_FLOCK_EXECUTABLE} $ENV{TRINITY_RAID_BUILD_LINK_LOCK}")
  if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang" AND CMAKE_AR)
    # GNU-compatible thin archives retain object references instead of copying
    # every large unity object into an intermediate .a. This keeps the
    # serialized archive step beneath the same coordinator/PSI gate while
    # avoiding the host pressure observed when libgame.a/libscripts.a were
    # materialized as ordinary archives.
    set(CMAKE_CXX_ARCHIVE_CREATE "<CMAKE_AR> qcT <TARGET> <LINK_FLAGS> <OBJECTS>")
    set(CMAKE_C_ARCHIVE_CREATE "<CMAKE_AR> qcT <TARGET> <LINK_FLAGS> <OBJECTS>")
    message(STATUS "Raid build coordinator: GNU-compatible thin intermediate archives enabled")
  endif()
  message(STATUS
    "Raid build coordinator ticket $ENV{TRINITY_RAID_BUILD_TICKET}: "
    "$ENV{TRINITY_RAID_BUILD_COMPILER_JOBS} compiler jobs, "
    "$ENV{TRINITY_RAID_BUILD_LINKER_JOBS} linker job")
endif()

# CMake policies (can not be handled elsewhere)
cmake_policy(SET CMP0005 NEW)
cmake_policy(SET CMP0043 NEW) # Ignore COMPILE_DEFINITIONS_<Config> properties
cmake_policy(SET CMP0054 NEW) # Only interpret if() arguments as variables or keywords when unquoted - prevents intepreting if(SOME_STRING_VARIABLE MATCHES "MSVC") as if(SOME_STRING_VARIABLE MATCHES "1")
cmake_policy(SET CMP0067 NEW) # Honor language standard in try_compile() source-file signature
cmake_policy(SET CMP0074 NEW) # find_package() uses <PackageName>_ROOT variables

if(POLICY CMP0144)
  cmake_policy(SET CMP0144 NEW) # find_package() uses upper-case <PACKAGENAME>_ROOT variables
endif()

if(POLICY CMP0153)
  cmake_policy(SET CMP0153 NEW) # The exec_program() command should not be called
endif()

# Set RPATH-handing (CMake parameters)
set(CMAKE_SKIP_BUILD_RPATH 0)
set(CMAKE_BUILD_WITH_INSTALL_RPATH 0)
list(APPEND CMAKE_INSTALL_RPATH "${CMAKE_INSTALL_PREFIX}/lib")
set(CMAKE_INSTALL_RPATH_USE_LINK_PATH 1)

# set macro-directory
list(APPEND CMAKE_MODULE_PATH
  "${CMAKE_SOURCE_DIR}/cmake/macros")

# build in Release-mode by default if not explicitly set
if(CMAKE_GENERATOR STREQUAL "Ninja Multi-Config")
  set(CMAKE_DEFAULT_BUILD_TYPE "RelWithDebInfo" CACHE INTERNAL "")
endif()
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE "RelWithDebInfo")
endif()

include(CheckCXXSourceRuns)
include(CheckIncludeFiles)
include(ConfigureScripts)

# set default buildoptions and print them
include(cmake/options.cmake)

# turn off PCH totally if enabled (hidden setting, mainly for devs)
if(NOPCH)
  set(USE_COREPCH 0)
  set(USE_SCRIPTPCH 0)
endif()

include(ConfigureBaseTargets)
include(CheckPlatform)

include(GroupSources)
include(AutoCollect)

find_package(PCHSupport)
find_package(MySQL)

if(NOT WITHOUT_GIT)
  find_package(Git 1.7)
endif()

# find mysql client binary (needed by genrev)
find_package(MySQL OPTIONAL_COMPONENTS binary)

# Find revision ID and hash of the sourcetree
include(cmake/genrev.cmake)

# print out the results before continuing
include(cmake/showoptions.cmake)

# add dependencies
add_subdirectory(dep)

# add core sources
add_subdirectory(src)

include(CTest)
if(BUILD_TESTING)
  list(APPEND CMAKE_MODULE_PATH
    "${Catch2_SOURCE_DIR}/contrib")
  include(Catch)

  add_subdirectory(tests)
  
  # Catch cmakefile messes with our settings we explicitly leave up to the user
  # restore user preference
  if (NOT WITH_SOURCE_TREE STREQUAL "hierarchical-folders")
    set_property(GLOBAL PROPERTY USE_FOLDERS OFF)
  endif()
endif()
