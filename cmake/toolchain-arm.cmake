# ARM Cross-Compilation Toolchain for Water Treatment Controller
# Copyright (C) 2024
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Usage: cmake -DCMAKE_TOOLCHAIN_FILE=cmake/toolchain-arm.cmake ..

set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR arm)

# Target architecture (override with -DARM_ARCH=...)
# Options: armv6, armv7, armv7hf, aarch64
if(NOT ARM_ARCH)
    set(ARM_ARCH "armv7hf")
endif()

# Toolchain prefix based on architecture
if(ARM_ARCH STREQUAL "aarch64")
    set(CMAKE_SYSTEM_PROCESSOR aarch64)
    set(TOOLCHAIN_PREFIX "aarch64-linux-gnu")
    set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -march=armv8-a")
elseif(ARM_ARCH STREQUAL "armv7hf")
    set(TOOLCHAIN_PREFIX "arm-linux-gnueabihf")
    set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -march=armv7-a -mfpu=neon -mfloat-abi=hard")
elseif(ARM_ARCH STREQUAL "armv7")
    set(TOOLCHAIN_PREFIX "arm-linux-gnueabi")
    set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -march=armv7-a -mfloat-abi=soft")
elseif(ARM_ARCH STREQUAL "armv6")
    set(TOOLCHAIN_PREFIX "arm-linux-gnueabihf")
    set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -march=armv6 -mfpu=vfp -mfloat-abi=hard")
else()
    message(FATAL_ERROR "Unknown ARM architecture: ${ARM_ARCH}")
endif()

# Find the cross compiler
find_program(CMAKE_C_COMPILER ${TOOLCHAIN_PREFIX}-gcc)
find_program(CMAKE_CXX_COMPILER ${TOOLCHAIN_PREFIX}-g++)
find_program(CMAKE_AR ${TOOLCHAIN_PREFIX}-ar)
find_program(CMAKE_RANLIB ${TOOLCHAIN_PREFIX}-ranlib)
find_program(CMAKE_STRIP ${TOOLCHAIN_PREFIX}-strip)
find_program(CMAKE_OBJCOPY ${TOOLCHAIN_PREFIX}-objcopy)

if(NOT CMAKE_C_COMPILER)
    message(WARNING "Cross compiler ${TOOLCHAIN_PREFIX}-gcc not found. "
                    "Please install: apt-get install gcc-${TOOLCHAIN_PREFIX}")
endif()

# Sysroot (can be overridden with -DCMAKE_SYSROOT=...)
if(NOT CMAKE_SYSROOT)
    # Try common locations
    if(EXISTS "/usr/${TOOLCHAIN_PREFIX}")
        set(CMAKE_SYSROOT "/usr/${TOOLCHAIN_PREFIX}")
    endif()
endif()

# Search paths
set(CMAKE_FIND_ROOT_PATH ${CMAKE_SYSROOT})
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)

# Common flags for embedded systems
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -ffunction-sections -fdata-sections")
set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -Wl,--gc-sections")

# Optimize for size in release builds
set(CMAKE_C_FLAGS_RELEASE "${CMAKE_C_FLAGS_RELEASE} -Os")

message(STATUS "ARM Cross-Compilation Configuration:")
message(STATUS "  Architecture: ${ARM_ARCH}")
message(STATUS "  Toolchain: ${TOOLCHAIN_PREFIX}")
message(STATUS "  C Compiler: ${CMAKE_C_COMPILER}")
message(STATUS "  Sysroot: ${CMAKE_SYSROOT}")
