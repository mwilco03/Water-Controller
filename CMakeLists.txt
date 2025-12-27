cmake_minimum_required(VERSION 3.16)
project(water_treat_controller VERSION 1.2.0 LANGUAGES C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# Include board auto-detection
include(${CMAKE_SOURCE_DIR}/cmake/board-detect.cmake)

# Configure board-specific settings
configure_board_settings()

# Build options
option(BUILD_TESTS "Build test suite" ON)
option(BUILD_SHARED_LIBS "Build shared libraries" ON)
option(ENABLE_SANITIZERS "Enable address and undefined behavior sanitizers" OFF)

# Compiler flags
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -Wall -Wextra -Wpedantic")
set(CMAKE_C_FLAGS_DEBUG "${CMAKE_C_FLAGS_DEBUG} -g -O0 -DDEBUG")
set(CMAKE_C_FLAGS_RELEASE "${CMAKE_C_FLAGS_RELEASE} -O3 -DNDEBUG")

if(ENABLE_SANITIZERS)
    set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -fsanitize=address,undefined")
    set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -fsanitize=address,undefined")
endif()

# Find required packages
find_package(Threads REQUIRED)
find_package(PkgConfig REQUIRED)

# Check for PostgreSQL
pkg_check_modules(LIBPQ libpq)
if(LIBPQ_FOUND)
    add_definitions(-DHAVE_POSTGRESQL)
endif()

# Check for JSON-C
pkg_check_modules(JSONC json-c)
if(NOT JSONC_FOUND)
    message(WARNING "json-c not found, using bundled implementation")
endif()

# Include directories
include_directories(
    ${CMAKE_SOURCE_DIR}/src
    ${CMAKE_SOURCE_DIR}/src/profinet
    ${CMAKE_SOURCE_DIR}/src/registry
    ${CMAKE_SOURCE_DIR}/src/control
    ${CMAKE_SOURCE_DIR}/src/alarms
    ${CMAKE_SOURCE_DIR}/src/historian
    ${CMAKE_SOURCE_DIR}/src/coordination
    ${CMAKE_SOURCE_DIR}/src/config
    ${CMAKE_SOURCE_DIR}/src/db
    ${CMAKE_SOURCE_DIR}/src/ipc
    ${CMAKE_SOURCE_DIR}/src/modbus
    ${CMAKE_SOURCE_DIR}/src/utils
)

# Core library sources
set(CORE_SOURCES
    src/utils/logger.c
    src/utils/time_utils.c
    src/utils/buffer.c
    src/utils/crc.c
    src/db/database.c
    src/config/config_manager.c
)

# PROFINET module sources
set(PROFINET_SOURCES
    src/profinet/profinet_controller.c
    src/profinet/dcp_discovery.c
    src/profinet/cyclic_exchange.c
    src/profinet/profinet_frame.c
    src/profinet/ar_manager.c
)

# Registry module sources
set(REGISTRY_SOURCES
    src/registry/rtu_registry.c
    src/registry/slot_manager.c
)

# Control module sources
set(CONTROL_SOURCES
    src/control/control_engine.c
    src/control/pid_loop.c
    src/control/sequence_engine.c
    src/control/interlock_manager.c
)

# Alarm module sources
set(ALARM_SOURCES
    src/alarms/alarm_manager.c
    src/alarms/alarm_rules.c
)

# Historian module sources
set(HISTORIAN_SOURCES
    src/historian/historian.c
    src/historian/compression.c
    src/historian/tag_manager.c
)

# Coordination module sources
set(COORDINATION_SOURCES
    src/coordination/cascade_control.c
    src/coordination/load_balance.c
    src/coordination/failover.c
    src/coordination/coordination.c
)

# IPC module sources
set(IPC_SOURCES
    src/ipc/ipc_server.c
)

# User module sources
set(USER_SOURCES
    src/user/user_sync.c
)

# Modbus module sources
set(MODBUS_SOURCES
    src/modbus/modbus_common.c
    src/modbus/modbus_tcp.c
    src/modbus/modbus_rtu.c
    src/modbus/register_map.c
    src/modbus/modbus_gateway.c
)

# Create core library
add_library(wtc_core ${CORE_SOURCES})
target_link_libraries(wtc_core Threads::Threads)
if(LIBPQ_FOUND)
    target_link_libraries(wtc_core ${LIBPQ_LIBRARIES})
    target_include_directories(wtc_core PRIVATE ${LIBPQ_INCLUDE_DIRS})
endif()
if(JSONC_FOUND)
    target_link_libraries(wtc_core ${JSONC_LIBRARIES})
    target_include_directories(wtc_core PRIVATE ${JSONC_INCLUDE_DIRS})
endif()

# Create PROFINET library
add_library(wtc_profinet ${PROFINET_SOURCES})
target_link_libraries(wtc_profinet wtc_core)

# Create registry library
add_library(wtc_registry ${REGISTRY_SOURCES})
target_link_libraries(wtc_registry wtc_core)

# Create control library
add_library(wtc_control ${CONTROL_SOURCES})
target_link_libraries(wtc_control wtc_core wtc_registry)

# Create alarm library
add_library(wtc_alarms ${ALARM_SOURCES})
target_link_libraries(wtc_alarms wtc_core wtc_registry)

# Create historian library
add_library(wtc_historian ${HISTORIAN_SOURCES})
target_link_libraries(wtc_historian wtc_core wtc_registry)

# Create coordination library
add_library(wtc_coordination ${COORDINATION_SOURCES})
target_link_libraries(wtc_coordination wtc_core wtc_registry wtc_control)

# Create user library
add_library(wtc_user ${USER_SOURCES})
target_link_libraries(wtc_user wtc_core)

# Create IPC library
add_library(wtc_ipc ${IPC_SOURCES})
target_link_libraries(wtc_ipc wtc_core wtc_registry wtc_alarms wtc_control wtc_user rt)

# Create Modbus library
add_library(wtc_modbus ${MODBUS_SOURCES})
target_link_libraries(wtc_modbus wtc_core wtc_registry wtc_control wtc_alarms)

# Main executable
add_executable(water_treat_controller src/main.c)
target_link_libraries(water_treat_controller
    wtc_core
    wtc_profinet
    wtc_registry
    wtc_control
    wtc_alarms
    wtc_historian
    wtc_coordination
    wtc_ipc
    wtc_modbus
    rt
    m
)

# Export board-specific definitions to main executable
export_board_definitions(water_treat_controller)

# Standalone Modbus Gateway executable
add_executable(modbus_gateway src/modbus/modbus_gateway_main.c)
target_link_libraries(modbus_gateway
    wtc_modbus
    wtc_core
    wtc_registry
    wtc_control
    wtc_alarms
    wtc_ipc
    rt
    m
    systemd
)
export_board_definitions(modbus_gateway)

# Tests
if(BUILD_TESTS)
    enable_testing()

    add_executable(test_profinet tests/test_profinet.c)
    target_link_libraries(test_profinet wtc_profinet wtc_core)
    add_test(NAME test_profinet COMMAND test_profinet)

    add_executable(test_control tests/test_control.c)
    target_link_libraries(test_control wtc_control wtc_core wtc_registry)
    add_test(NAME test_control COMMAND test_control)

    add_executable(test_alarms tests/test_alarms.c)
    target_link_libraries(test_alarms wtc_alarms wtc_core wtc_registry)
    add_test(NAME test_alarms COMMAND test_alarms)

    add_executable(test_historian tests/test_historian.c)
    target_link_libraries(test_historian wtc_historian wtc_core wtc_registry)
    add_test(NAME test_historian COMMAND test_historian)

    add_executable(test_registry tests/test_registry.c)
    target_link_libraries(test_registry wtc_registry wtc_core)
    add_test(NAME test_registry COMMAND test_registry)
endif()

# Installation
install(TARGETS water_treat_controller modbus_gateway
    RUNTIME DESTINATION bin
)

install(TARGETS wtc_core wtc_profinet wtc_registry wtc_control wtc_alarms wtc_historian wtc_coordination wtc_modbus
    LIBRARY DESTINATION lib
    ARCHIVE DESTINATION lib
)

install(DIRECTORY src/
    DESTINATION include/water_treat_controller
    FILES_MATCHING PATTERN "*.h"
)

# CPack configuration
set(CPACK_PACKAGE_NAME "water-treat-controller")
set(CPACK_PACKAGE_VERSION ${PROJECT_VERSION})
set(CPACK_PACKAGE_DESCRIPTION_SUMMARY "PROFINET Controller for Water Treatment RTU Network")
include(CPack)
