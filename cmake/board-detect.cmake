# Board Auto-Detection for Water Treatment Controller
# Copyright (C) 2024
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Automatically detects the target board and configures appropriate settings

# Board type enum
set(BOARD_UNKNOWN 0)
set(BOARD_X86_64 1)
set(BOARD_RPI3 2)
set(BOARD_RPI4 3)
set(BOARD_RPI5 4)
set(BOARD_RPI_ZERO 5)
set(BOARD_ORANGE_PI_ZERO 6)
set(BOARD_ORANGE_PI_PC 7)
set(BOARD_ORANGE_PI_5 8)
set(BOARD_LE_POTATO 9)
set(BOARD_LUCKFOX_LYRA 10)
set(BOARD_BEAGLEBONE 11)
set(BOARD_ODROID_XU4 12)
set(BOARD_ODROID_C2 13)
set(BOARD_ODROID_N2 14)

# Default to unknown
if(NOT DEFINED DETECTED_BOARD)
    set(DETECTED_BOARD ${BOARD_UNKNOWN})
endif()

# Auto-detect board if not cross-compiling
if(NOT CMAKE_CROSSCOMPILING)
    # Check CPU architecture
    execute_process(COMMAND uname -m OUTPUT_VARIABLE ARCH OUTPUT_STRIP_TRAILING_WHITESPACE)

    if(ARCH STREQUAL "x86_64")
        set(DETECTED_BOARD ${BOARD_X86_64})
        set(BOARD_NAME "x86_64")
        message(STATUS "Detected x86_64 platform")

    elseif(ARCH MATCHES "aarch64|arm64")
        # ARM64 - check specific board
        if(EXISTS "/proc/device-tree/model")
            file(READ "/proc/device-tree/model" BOARD_MODEL)

            if(BOARD_MODEL MATCHES "Raspberry Pi 5")
                set(DETECTED_BOARD ${BOARD_RPI5})
                set(BOARD_NAME "Raspberry Pi 5")
            elseif(BOARD_MODEL MATCHES "Raspberry Pi 4")
                set(DETECTED_BOARD ${BOARD_RPI4})
                set(BOARD_NAME "Raspberry Pi 4")
            elseif(BOARD_MODEL MATCHES "Orange Pi 5")
                set(DETECTED_BOARD ${BOARD_ORANGE_PI_5})
                set(BOARD_NAME "Orange Pi 5")
            elseif(BOARD_MODEL MATCHES "Libre Computer AML-S905X-CC")
                set(DETECTED_BOARD ${BOARD_LE_POTATO})
                set(BOARD_NAME "Le Potato")
            elseif(BOARD_MODEL MATCHES "ODROID-C2")
                set(DETECTED_BOARD ${BOARD_ODROID_C2})
                set(BOARD_NAME "ODROID-C2")
            elseif(BOARD_MODEL MATCHES "ODROID-N2")
                set(DETECTED_BOARD ${BOARD_ODROID_N2})
                set(BOARD_NAME "ODROID-N2")
            else()
                set(BOARD_NAME "Generic ARM64")
            endif()
        else()
            set(BOARD_NAME "Generic ARM64")
        endif()
        message(STATUS "Detected ARM64 board: ${BOARD_NAME}")

    elseif(ARCH MATCHES "armv7l|armv7")
        # ARMv7 - check specific board
        if(EXISTS "/proc/device-tree/model")
            file(READ "/proc/device-tree/model" BOARD_MODEL)

            if(BOARD_MODEL MATCHES "Raspberry Pi 3")
                set(DETECTED_BOARD ${BOARD_RPI3})
                set(BOARD_NAME "Raspberry Pi 3")
            elseif(BOARD_MODEL MATCHES "Orange Pi Zero")
                set(DETECTED_BOARD ${BOARD_ORANGE_PI_ZERO})
                set(BOARD_NAME "Orange Pi Zero")
            elseif(BOARD_MODEL MATCHES "Orange Pi PC")
                set(DETECTED_BOARD ${BOARD_ORANGE_PI_PC})
                set(BOARD_NAME "Orange Pi PC")
            elseif(BOARD_MODEL MATCHES "BeagleBone")
                set(DETECTED_BOARD ${BOARD_BEAGLEBONE})
                set(BOARD_NAME "BeagleBone")
            elseif(BOARD_MODEL MATCHES "ODROID-XU4" OR BOARD_MODEL MATCHES "ODROID-XU3")
                set(DETECTED_BOARD ${BOARD_ODROID_XU4})
                set(BOARD_NAME "ODROID-XU4")
            else()
                set(BOARD_NAME "Generic ARMv7")
            endif()
        else()
            set(BOARD_NAME "Generic ARMv7")
        endif()
        message(STATUS "Detected ARMv7 board: ${BOARD_NAME}")

    elseif(ARCH MATCHES "armv6l|armv6")
        # ARMv6 - Raspberry Pi Zero or Luckfox
        if(EXISTS "/proc/device-tree/model")
            file(READ "/proc/device-tree/model" BOARD_MODEL)

            if(BOARD_MODEL MATCHES "Raspberry Pi Zero")
                set(DETECTED_BOARD ${BOARD_RPI_ZERO})
                set(BOARD_NAME "Raspberry Pi Zero")
            elseif(BOARD_MODEL MATCHES "Luckfox")
                set(DETECTED_BOARD ${BOARD_LUCKFOX_LYRA})
                set(BOARD_NAME "Luckfox Lyra")
            else()
                set(BOARD_NAME "Generic ARMv6")
            endif()
        else()
            set(BOARD_NAME "Generic ARMv6")
        endif()
        message(STATUS "Detected ARMv6 board: ${BOARD_NAME}")
    endif()
endif()

# Board-specific configuration
function(configure_board_settings)
    message(STATUS "Configuring for board: ${BOARD_NAME}")

    # Set board-specific compiler flags
    if(DETECTED_BOARD EQUAL ${BOARD_RPI5})
        set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -mcpu=cortex-a76" PARENT_SCOPE)
        set(BOARD_HAS_PCIE TRUE PARENT_SCOPE)
        set(BOARD_GPIO_CHIP "pinctrl-rp1" PARENT_SCOPE)

    elseif(DETECTED_BOARD EQUAL ${BOARD_RPI4})
        set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -mcpu=cortex-a72" PARENT_SCOPE)
        set(BOARD_GPIO_CHIP "pinctrl-bcm2711" PARENT_SCOPE)

    elseif(DETECTED_BOARD EQUAL ${BOARD_RPI3})
        set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -mcpu=cortex-a53" PARENT_SCOPE)
        set(BOARD_GPIO_CHIP "pinctrl-bcm2835" PARENT_SCOPE)

    elseif(DETECTED_BOARD EQUAL ${BOARD_ORANGE_PI_5})
        set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -mcpu=cortex-a55" PARENT_SCOPE)
        set(BOARD_GPIO_CHIP "gpio-rockchip" PARENT_SCOPE)

    elseif(DETECTED_BOARD EQUAL ${BOARD_LE_POTATO})
        set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -mcpu=cortex-a53" PARENT_SCOPE)
        set(BOARD_GPIO_CHIP "gpio-meson" PARENT_SCOPE)

    elseif(DETECTED_BOARD EQUAL ${BOARD_LUCKFOX_LYRA})
        # Luckfox Lyra uses Rockchip RV1103/RV1106
        set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -march=armv7-a -mfpu=neon" PARENT_SCOPE)
        set(BOARD_GPIO_CHIP "gpio-rockchip" PARENT_SCOPE)
        set(BOARD_HAS_NPU TRUE PARENT_SCOPE)  # Has AI accelerator

    elseif(DETECTED_BOARD EQUAL ${BOARD_ORANGE_PI_ZERO})
        set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -mcpu=cortex-a7 -mfpu=neon-vfpv4" PARENT_SCOPE)
        set(BOARD_GPIO_CHIP "gpio-sunxi" PARENT_SCOPE)

    elseif(DETECTED_BOARD EQUAL ${BOARD_BEAGLEBONE})
        set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -mcpu=cortex-a8 -mfpu=neon" PARENT_SCOPE)
        set(BOARD_GPIO_CHIP "gpio-omap" PARENT_SCOPE)

    elseif(DETECTED_BOARD EQUAL ${BOARD_ODROID_XU4})
        # ODROID-XU4: Samsung Exynos 5422 (Cortex-A15 + Cortex-A7 big.LITTLE)
        set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -mcpu=cortex-a15 -mfpu=neon-vfpv4" PARENT_SCOPE)
        set(BOARD_GPIO_CHIP "gpio-samsung" PARENT_SCOPE)
        set(BOARD_HAS_EMMC TRUE PARENT_SCOPE)

    elseif(DETECTED_BOARD EQUAL ${BOARD_ODROID_C2})
        # ODROID-C2: Amlogic S905 (Cortex-A53)
        set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -mcpu=cortex-a53" PARENT_SCOPE)
        set(BOARD_GPIO_CHIP "gpio-meson" PARENT_SCOPE)

    elseif(DETECTED_BOARD EQUAL ${BOARD_ODROID_N2})
        # ODROID-N2: Amlogic S922X (Cortex-A73 + Cortex-A53 big.LITTLE)
        set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -mcpu=cortex-a73" PARENT_SCOPE)
        set(BOARD_GPIO_CHIP "gpio-meson" PARENT_SCOPE)
        set(BOARD_HAS_EMMC TRUE PARENT_SCOPE)
    endif()

    # Set I2C bus paths based on board
    if(DETECTED_BOARD EQUAL ${BOARD_RPI5} OR
       DETECTED_BOARD EQUAL ${BOARD_RPI4} OR
       DETECTED_BOARD EQUAL ${BOARD_RPI3})
        set(DEFAULT_I2C_BUS "/dev/i2c-1" PARENT_SCOPE)
    elseif(DETECTED_BOARD EQUAL ${BOARD_ORANGE_PI_5})
        set(DEFAULT_I2C_BUS "/dev/i2c-3" PARENT_SCOPE)
    elseif(DETECTED_BOARD EQUAL ${BOARD_LUCKFOX_LYRA})
        set(DEFAULT_I2C_BUS "/dev/i2c-0" PARENT_SCOPE)
    elseif(DETECTED_BOARD EQUAL ${BOARD_ODROID_XU4})
        # ODROID-XU4 uses I2C-1 on the GPIO header (pins 3/5)
        set(DEFAULT_I2C_BUS "/dev/i2c-1" PARENT_SCOPE)
    elseif(DETECTED_BOARD EQUAL ${BOARD_ODROID_C2} OR
           DETECTED_BOARD EQUAL ${BOARD_ODROID_N2})
        # ODROID-C2/N2 use I2C-1 on the 40-pin header
        set(DEFAULT_I2C_BUS "/dev/i2c-1" PARENT_SCOPE)
    else()
        set(DEFAULT_I2C_BUS "/dev/i2c-1" PARENT_SCOPE)
    endif()

    # Set 1-Wire path
    set(ONEWIRE_PATH "/sys/bus/w1/devices" PARENT_SCOPE)
endfunction()

# Export board info as compile definitions
function(export_board_definitions TARGET)
    target_compile_definitions(${TARGET} PRIVATE
        BOARD_TYPE=${DETECTED_BOARD}
        BOARD_NAME="${BOARD_NAME}"
    )

    if(DEFINED DEFAULT_I2C_BUS)
        target_compile_definitions(${TARGET} PRIVATE
            DEFAULT_I2C_BUS="${DEFAULT_I2C_BUS}"
        )
    endif()

    if(DEFINED BOARD_GPIO_CHIP)
        target_compile_definitions(${TARGET} PRIVATE
            BOARD_GPIO_CHIP="${BOARD_GPIO_CHIP}"
        )
    endif()

    if(BOARD_HAS_NPU)
        target_compile_definitions(${TARGET} PRIVATE BOARD_HAS_NPU=1)
    endif()

    if(BOARD_HAS_PCIE)
        target_compile_definitions(${TARGET} PRIVATE BOARD_HAS_PCIE=1)
    endif()

    if(BOARD_HAS_EMMC)
        target_compile_definitions(${TARGET} PRIVATE BOARD_HAS_EMMC=1)
    endif()
endfunction()
