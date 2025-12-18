# Luckfox Lyra Cross-Compilation Toolchain
# Copyright (C) 2024
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Luckfox Lyra uses Rockchip RV1103/RV1106 (ARM Cortex-A7)
#
# Usage: cmake -DCMAKE_TOOLCHAIN_FILE=cmake/toolchain-luckfox.cmake ..
#
# Prerequisites:
#   - Luckfox SDK or ARM cross-compiler
#   - Download from: https://github.com/luckfox-eng29/luckfox-pico
#
# Install toolchain:
#   sudo apt install gcc-arm-linux-gnueabihf g++-arm-linux-gnueabihf

set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR arm)

# Luckfox Lyra board type
set(DETECTED_BOARD 10)  # BOARD_LUCKFOX_LYRA
set(BOARD_NAME "Luckfox Lyra")

# Toolchain prefix
set(TOOLCHAIN_PREFIX "arm-linux-gnueabihf")

# Find cross compiler
find_program(CMAKE_C_COMPILER ${TOOLCHAIN_PREFIX}-gcc)
find_program(CMAKE_CXX_COMPILER ${TOOLCHAIN_PREFIX}-g++)
find_program(CMAKE_AR ${TOOLCHAIN_PREFIX}-ar)
find_program(CMAKE_RANLIB ${TOOLCHAIN_PREFIX}-ranlib)
find_program(CMAKE_STRIP ${TOOLCHAIN_PREFIX}-strip)
find_program(CMAKE_OBJCOPY ${TOOLCHAIN_PREFIX}-objcopy)

# Check if Luckfox SDK toolchain is available
if(DEFINED ENV{LUCKFOX_SDK_PATH})
    set(LUCKFOX_TOOLCHAIN "$ENV{LUCKFOX_SDK_PATH}/tools/linux/toolchain/arm-rockchip830-linux-uclibcgnueabihf")
    if(EXISTS "${LUCKFOX_TOOLCHAIN}")
        set(CMAKE_C_COMPILER "${LUCKFOX_TOOLCHAIN}/bin/arm-rockchip830-linux-uclibcgnueabihf-gcc")
        set(CMAKE_CXX_COMPILER "${LUCKFOX_TOOLCHAIN}/bin/arm-rockchip830-linux-uclibcgnueabihf-g++")
        set(CMAKE_SYSROOT "${LUCKFOX_TOOLCHAIN}/arm-rockchip830-linux-uclibcgnueabihf/sysroot")
        message(STATUS "Using Luckfox SDK toolchain")
    endif()
endif()

if(NOT CMAKE_C_COMPILER)
    message(WARNING "Cross compiler not found. Install with: apt install gcc-arm-linux-gnueabihf")
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

# Luckfox Lyra (RV1103/RV1106) specific flags
# - ARM Cortex-A7 with NEON
# - Limited RAM (64MB-256MB depending on model)
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -march=armv7-a -mtune=cortex-a7 -mfpu=neon-vfpv4 -mfloat-abi=hard")

# Optimize for small memory footprint
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -ffunction-sections -fdata-sections")
set(CMAKE_C_FLAGS_RELEASE "${CMAKE_C_FLAGS_RELEASE} -Os -DNDEBUG")
set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -Wl,--gc-sections -Wl,--as-needed")

# Luckfox-specific definitions
add_definitions(-DLUCKFOX_LYRA)
add_definitions(-DBOARD_HAS_NPU=1)  # RV1103/RV1106 have NPU

# Default I2C bus on Luckfox
set(DEFAULT_I2C_BUS "/dev/i2c-0")

# GPIO chip for Luckfox (Rockchip)
set(BOARD_GPIO_CHIP "gpio-rockchip")

message(STATUS "Luckfox Lyra Cross-Compilation Configuration:")
message(STATUS "  C Compiler: ${CMAKE_C_COMPILER}")
message(STATUS "  Sysroot: ${CMAKE_SYSROOT}")
message(STATUS "  I2C Bus: ${DEFAULT_I2C_BUS}")
