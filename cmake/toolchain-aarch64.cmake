# AArch64 (ARM64) Cross-Compilation Toolchain for Water Treatment Controller
# Copyright (C) 2024
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Usage: cmake -DCMAKE_TOOLCHAIN_FILE=cmake/toolchain-aarch64.cmake ..

set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR aarch64)

# Toolchain prefix
set(TOOLCHAIN_PREFIX "aarch64-linux-gnu")

# Find the cross compiler
find_program(CMAKE_C_COMPILER ${TOOLCHAIN_PREFIX}-gcc)
find_program(CMAKE_CXX_COMPILER ${TOOLCHAIN_PREFIX}-g++)
find_program(CMAKE_AR ${TOOLCHAIN_PREFIX}-ar)
find_program(CMAKE_RANLIB ${TOOLCHAIN_PREFIX}-ranlib)
find_program(CMAKE_STRIP ${TOOLCHAIN_PREFIX}-strip)
find_program(CMAKE_OBJCOPY ${TOOLCHAIN_PREFIX}-objcopy)

if(NOT CMAKE_C_COMPILER)
    message(WARNING "Cross compiler ${TOOLCHAIN_PREFIX}-gcc not found. "
                    "Please install: apt-get install gcc-aarch64-linux-gnu")
endif()

# Sysroot
if(NOT CMAKE_SYSROOT)
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

# ARM64 specific flags
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -march=armv8-a")
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -ffunction-sections -fdata-sections")
set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -Wl,--gc-sections")

# Optimize for size in release builds
set(CMAKE_C_FLAGS_RELEASE "${CMAKE_C_FLAGS_RELEASE} -Os")

message(STATUS "AArch64 Cross-Compilation Configuration:")
message(STATUS "  C Compiler: ${CMAKE_C_COMPILER}")
message(STATUS "  Sysroot: ${CMAKE_SYSROOT}")
