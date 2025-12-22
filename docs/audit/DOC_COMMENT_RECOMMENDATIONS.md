# Missing Doc Comment Recommendations

This document identifies undocumented public interfaces in both Water-Controller and Water-Treat repositories, with specific recommendations for documentation.

---

## Water-Controller Repository

### Critical (Safety-Related Functions)

#### `src/control/interlock_manager.c`

##### `wtc_result_t create_low_level_interlock(...)`
**Current:** No documentation
**Recommended:**
```c
/**
 * @brief Create a low-level pump protection interlock.
 *
 * Configures an interlock that forces a pump OFF when the monitored level
 * sensor drops below the threshold. Prevents pump cavitation and dry-running.
 *
 * @param[in] engine          Control engine context
 * @param[in] level_rtu       RTU station name for level sensor
 * @param[in] level_slot      Slot number of level sensor
 * @param[in] pump_rtu        RTU station name for pump actuator
 * @param[in] pump_slot       Slot number of pump actuator
 * @param[in] threshold       Low level threshold (e.g., 10.0 for 10%)
 *
 * @return WTC_OK on success, WTC_ERROR_INVALID_PARAM if RTU not found,
 *         WTC_ERROR_SLOT_NOT_FOUND if slot invalid
 *
 * @note Delay: 5000ms to prevent nuisance trips from wave action
 * @note Action: FORCE_OFF - pump will not restart until level recovers
 *       AND interlock is reset
 *
 * @safety CRITICAL - This interlock protects equipment from damage.
 *         Do not modify without engineering review.
 */
```

##### `wtc_result_t create_high_pressure_interlock(...)`
**Current:** Brief comment only
**Recommended:**
```c
/**
 * @brief Create a high-pressure pump protection interlock.
 *
 * Configures an interlock that forces a pump OFF when downstream pressure
 * exceeds the threshold. Prevents pipe burst and equipment damage.
 *
 * @param[in] engine           Control engine context
 * @param[in] pressure_rtu     RTU station name for pressure sensor
 * @param[in] pressure_slot    Slot number of pressure sensor
 * @param[in] pump_rtu         RTU station name for pump actuator
 * @param[in] pump_slot        Slot number of pump actuator
 * @param[in] threshold        High pressure threshold in bar (e.g., 10.0)
 *
 * @return WTC_OK on success, negative error code on failure
 *
 * @note Delay: 1000ms - fast response for safety
 * @note Action: FORCE_OFF immediately
 *
 * @warning This is a CRITICAL safety interlock. The 1-second delay
 *          provides minimal debouncing while ensuring rapid response
 *          to dangerous pressure conditions.
 */
```

---

### High Priority (Public API Functions)

#### `src/profinet/profinet_controller.c`

##### `wtc_result_t profinet_controller_init(...)`
**Recommended:**
```c
/**
 * @brief Initialize the PROFINET IO Controller.
 *
 * Sets up the PROFINET stack, configures network parameters, and prepares
 * for device discovery. Must be called before any other profinet_* functions.
 *
 * @param[out] controller      Pointer to controller context to initialize
 * @param[in]  config          Configuration parameters (interface, cycle time, etc.)
 *
 * @return WTC_OK on success
 * @return WTC_ERROR_NETWORK if interface not found or not accessible
 * @return WTC_ERROR_CONFIG if configuration invalid
 * @return WTC_ERROR_MEMORY if allocation failed
 *
 * @pre config->interface must be a valid network interface name
 * @pre Caller must have CAP_NET_RAW and CAP_NET_ADMIN capabilities
 *
 * @post On success, controller is in INITIALIZED state, ready for start()
 * @post On failure, controller is in undefined state and should not be used
 *
 * @note Thread safety: UNSAFE - call only from main thread during startup
 * @note Memory: ALLOCATES - caller must call profinet_controller_cleanup()
 */
```

##### `wtc_result_t profinet_controller_start(...)`
**Recommended:**
```c
/**
 * @brief Start the PROFINET IO Controller.
 *
 * Begins network communication, initiates DCP discovery, and starts
 * processing cyclic I/O data. This is a non-blocking call; I/O processing
 * occurs in a background thread.
 *
 * @param[in] controller   Initialized controller context
 *
 * @return WTC_OK on success
 * @return WTC_ERROR_NOT_INITIALIZED if controller not initialized
 * @return WTC_ERROR_ALREADY_RUNNING if already started
 *
 * @pre profinet_controller_init() must have succeeded
 * @post Controller is in RUNNING state
 * @post Background thread is processing I/O
 *
 * @note Thread safety: SAFE - can be called from any thread
 */
```

#### `src/registry/rtu_registry.c`

##### `wtc_result_t rtu_registry_add_device(...)`
**Recommended:**
```c
/**
 * @brief Register a new RTU device in the registry.
 *
 * Adds an RTU device to the internal registry, allocating storage for
 * its sensors and actuators. The device is initially in OFFLINE state.
 *
 * @param[in,out] registry     Registry context
 * @param[in]     station_name PROFINET station name (max 63 chars)
 * @param[in]     ip_address   IP address string (e.g., "192.168.1.100")
 * @param[in]     vendor_id    PROFINET vendor ID
 * @param[in]     device_id    PROFINET device ID
 * @param[out]    device_id_out If non-NULL, receives assigned device ID
 *
 * @return WTC_OK on success
 * @return WTC_ERROR_ALREADY_EXISTS if station_name already registered
 * @return WTC_ERROR_MEMORY if allocation failed
 * @return WTC_ERROR_CAPACITY if registry at maximum capacity
 *
 * @note Thread safety: LOCK_REQUIRED - caller must hold registry mutex
 *       OR use rtu_registry_add_device_safe() for automatic locking
 */
```

##### `sensor_data_t* rtu_registry_get_sensor(...)`
**Recommended:**
```c
/**
 * @brief Get current sensor data from an RTU.
 *
 * Retrieves the most recent sensor reading for a specific slot on an RTU.
 * The returned data includes value, quality, and timestamp.
 *
 * @param[in] registry      Registry context
 * @param[in] station_name  RTU station name
 * @param[in] slot          Slot number (0-indexed)
 *
 * @return Pointer to sensor data, or NULL if not found
 *
 * @note The returned pointer is valid until the next registry modification.
 *       Copy data if needed beyond the current operation.
 * @note Thread safety: LOCK_REQUIRED - hold registry mutex while accessing
 *       returned data
 *
 * @warning Check returned quality before using value. BAD quality
 *          indicates the value should not be trusted.
 */
```

#### `src/alarms/alarm_manager.c`

##### `wtc_result_t alarm_manager_add_rule(...)`
**Recommended:**
```c
/**
 * @brief Add a new alarm rule to the alarm manager.
 *
 * Creates an alarm rule that monitors a sensor value and generates
 * alarms when thresholds are exceeded. Rules are evaluated on every
 * scan cycle.
 *
 * @param[in,out] mgr          Alarm manager context
 * @param[in]     rule         Rule configuration (copied internally)
 * @param[out]    rule_id      If non-NULL, receives assigned rule ID
 *
 * @return WTC_OK on success
 * @return WTC_ERROR_INVALID_PARAM if rule configuration invalid
 * @return WTC_ERROR_MEMORY if allocation failed
 *
 * @note Rules take effect immediately after this call returns.
 * @note Thread safety: SAFE - internal locking
 *
 * @see alarm_rule_t for rule configuration options
 * @see ISA-18.2 for alarm management best practices
 */
```

##### `wtc_result_t alarm_manager_acknowledge(...)`
**Recommended:**
```c
/**
 * @brief Acknowledge an active alarm.
 *
 * Transitions an alarm from ACTIVE_UNACK to ACTIVE_ACK state,
 * indicating an operator has seen and acknowledged the condition.
 * Records the acknowledging user and timestamp.
 *
 * @param[in,out] mgr        Alarm manager context
 * @param[in]     alarm_id   ID of alarm to acknowledge
 * @param[in]     username   Name of acknowledging user (for audit)
 *
 * @return WTC_OK on success
 * @return WTC_ERROR_NOT_FOUND if alarm_id not found
 * @return WTC_ERROR_INVALID_STATE if alarm already acknowledged or cleared
 *
 * @note Per ISA-18.2: Acknowledgment does not clear the alarm.
 *       The alarm will transition to CLEARED_UNACK when the condition
 *       returns to normal, then to CLEARED after a second acknowledgment.
 *
 * @note Thread safety: SAFE - internal locking
 * @note Audit: This operation is logged with timestamp and username
 */
```

---

### Medium Priority (Internal but Important)

#### `src/historian/historian.c`

##### `wtc_result_t historian_store_sample(...)`
**Recommended:**
```c
/**
 * @brief Store a sensor sample in the historian.
 *
 * Applies compression algorithm (if configured) and stores the sample
 * if it meets the storage criteria. Compression may discard samples
 * that fall within the deadband of the previous stored value.
 *
 * @param[in,out] hist       Historian context
 * @param[in]     tag_id     Historian tag ID
 * @param[in]     value      Sample value
 * @param[in]     quality    Data quality (GOOD, UNCERTAIN, BAD)
 * @param[in]     timestamp  Sample timestamp (microseconds since epoch)
 *
 * @return WTC_OK if sample stored or compressed away
 * @return WTC_ERROR_NOT_FOUND if tag_id not registered
 * @return WTC_ERROR_DATABASE if storage failed
 *
 * @note Quality is always stored; compression does not discard
 *       samples where quality changes even if value is within deadband.
 * @note Thread safety: SAFE - internal locking per tag
 */
```

##### `wtc_result_t historian_query_range(...)`
**Recommended:**
```c
/**
 * @brief Query historical data for a time range.
 *
 * Retrieves samples from the historian database for the specified
 * tag and time range. Results are ordered by timestamp ascending.
 *
 * @param[in]  hist         Historian context
 * @param[in]  tag_id       Historian tag ID
 * @param[in]  start_time   Start of range (microseconds since epoch)
 * @param[in]  end_time     End of range (microseconds since epoch)
 * @param[out] samples      Array to receive samples (caller allocates)
 * @param[in]  max_samples  Maximum samples to return
 * @param[out] count        Actual number of samples returned
 *
 * @return WTC_OK on success (even if 0 samples found)
 * @return WTC_ERROR_NOT_FOUND if tag_id not registered
 * @return WTC_ERROR_DATABASE on query error
 *
 * @note If more samples exist than max_samples, only the first
 *       max_samples are returned. Use pagination for large queries.
 * @note Thread safety: SAFE - read-only with snapshot isolation
 */
```

#### `src/modbus/modbus_gateway.c`

##### `wtc_result_t modbus_gateway_init(...)`
**Recommended:**
```c
/**
 * @brief Initialize the Modbus gateway.
 *
 * Sets up the PROFINET-to-Modbus gateway, including TCP server
 * and optional RTU client. The gateway translates between PROFINET
 * cyclic data and Modbus register access.
 *
 * @param[out] gateway    Gateway context to initialize
 * @param[in]  config     Gateway configuration
 * @param[in]  registry   RTU registry for PROFINET data access
 *
 * @return WTC_OK on success
 * @return WTC_ERROR_CONFIG if configuration invalid
 * @return WTC_ERROR_NETWORK if bind failed
 *
 * @note TCP server binds to configured address (default: 0.0.0.0:502)
 * @note Requires root or CAP_NET_BIND_SERVICE for port 502
 * @note Thread safety: UNSAFE - call during startup only
 */
```

---

## Water-Treat Repository

### Critical (Safety-Related Functions)

#### `src/alarms/alarm_manager.c`

##### `result_t alarm_check_interlock(...)`
**Recommended:**
```c
/**
 * @brief Evaluate and execute interlock action for an alarm.
 *
 * When an alarm with interlock enabled trips, this function
 * forces the target actuator to its configured safe state.
 * This executes LOCALLY on the RTU, independent of controller.
 *
 * @param[in] mgr         Alarm manager context
 * @param[in] rule        Triggered alarm rule
 * @param[in] sensor_val  Current sensor value that triggered alarm
 *
 * @return RESULT_OK if interlock action executed
 * @return RESULT_ERROR if actuator control failed
 *
 * @safety CRITICAL - This function executes safety interlocks.
 *         It MUST operate even when PROFINET communication is lost.
 *
 * @note Interlock actions:
 *       - INTERLOCK_ACTION_OFF: Force actuator OFF
 *       - INTERLOCK_ACTION_ON: Force actuator ON
 *       - INTERLOCK_ACTION_PWM: Set to specific duty cycle
 *
 * @note Release behavior depends on rule.release_on_clear:
 *       - true: Release to controller when alarm clears
 *       - false: Require manual reset
 */
```

#### `src/actuators/actuator_manager.c`

##### `result_t actuator_manager_handle_output(...)`
**Recommended:**
```c
/**
 * @brief Process PROFINET output data and control actuator.
 *
 * Receives output commands from PROFINET cyclic data and applies
 * them to the physical actuator (GPIO/PWM). Enforces safety limits
 * including max on-time and minimum cycle time.
 *
 * @param[in,out] mgr       Actuator manager context
 * @param[in]     slot      PROFINET slot number
 * @param[in]     data      Output data (4 bytes: command, duty, reserved)
 * @param[in]     length    Data length (must be 4)
 *
 * @return RESULT_OK on success
 * @return RESULT_ERROR if actuator not found or control failed
 * @return RESULT_BLOCKED if interlock is active on this actuator
 *
 * @note Output data format:
 *       Byte 0: Command (0x00=OFF, 0x01=ON, 0x02=PWM)
 *       Byte 1: PWM duty cycle (0-255)
 *       Bytes 2-3: Reserved
 *
 * @note If an interlock is active on this actuator, the command
 *       is ignored and the interlock state is maintained.
 *
 * @safety Commands are validated against safety limits before execution.
 */
```

##### `void actuator_watchdog_thread(...)`
**Recommended:**
```c
/**
 * @brief Actuator safety watchdog thread function.
 *
 * Monitors all actuators for safety limit violations:
 * - Maximum on-time exceeded
 * - Controller communication timeout
 *
 * Runs continuously at 100ms intervals, independent of PROFINET cycle.
 *
 * @param[in] arg   Actuator manager context (cast to actuator_manager_t*)
 *
 * @safety CRITICAL - This thread must not be blocked or delayed.
 *         It provides last-line protection for actuator safety limits.
 *
 * @note If max_on_time exceeded, actuator is forced OFF automatically.
 * @note If communication lost, degraded mode is entered.
 */
```

---

### High Priority (Public API Functions)

#### `src/profinet/profinet_manager.c`

##### `result_t profinet_manager_init(...)`
**Recommended:**
```c
/**
 * @brief Initialize the PROFINET I/O Device stack.
 *
 * Sets up the p-net PROFINET stack, configures device identity,
 * and prepares I/O modules for communication with the controller.
 *
 * @param[out] mgr      Manager context to initialize
 * @param[in]  config   PROFINET configuration (station name, IDs, etc.)
 *
 * @return RESULT_OK on success
 * @return RESULT_ERROR if p-net initialization failed
 * @return RESULT_ERROR_CONFIG if configuration invalid
 *
 * @note Station name is auto-generated from MAC if not configured.
 * @note Device must be discoverable via DCP after start().
 *
 * @pre Must be called before profinet_manager_start()
 * @pre Requires root privileges for raw socket access
 */
```

##### `result_t profinet_manager_set_input_data(...)`
**Recommended:**
```c
/**
 * @brief Set sensor data for PROFINET cyclic transmission.
 *
 * Updates the input data buffer for a sensor slot. Data is transmitted
 * to the controller on the next cyclic I/O exchange.
 *
 * @param[in] mgr      PROFINET manager context
 * @param[in] slot     Slot number (1-8 for sensors)
 * @param[in] value    Sensor value (IEEE 754 float)
 * @param[in] quality  Data quality code (QUALITY_GOOD, etc.)
 *
 * @return RESULT_OK on success
 * @return RESULT_ERROR_SLOT if slot not configured
 *
 * @note Data format: 5 bytes (4-byte float BE + 1-byte quality)
 * @note Thread safety: SAFE - uses internal locking
 *
 * @see PROFINET_DATA_FORMAT_SPECIFICATION.md for format details
 */
```

#### `src/sensors/sensor_manager.c`

##### `result_t sensor_manager_reload_sensors(...)`
**Recommended:**
```c
/**
 * @brief Reload sensor configuration from database.
 *
 * Queries the database for all configured sensors and updates
 * the sensor manager's internal list. Called at startup and
 * after configuration changes via TUI.
 *
 * @param[in,out] mgr   Sensor manager context
 *
 * @return RESULT_OK on success
 * @return RESULT_ERROR_DB if database query failed
 *
 * @note Existing sensor instances are updated, not recreated.
 * @note New sensors begin polling immediately.
 * @note Removed sensors stop polling and are deallocated.
 *
 * @note Thread safety: SAFE - acquires internal lock
 */
```

##### `result_t sensor_instance_read_with_quality(...)`
**Recommended:**
```c
/**
 * @brief Read sensor value with quality determination.
 *
 * Reads the current sensor value and determines data quality
 * based on:
 * - Consecutive failure count
 * - Data age (staleness)
 * - Value range validation
 *
 * @param[in]  sensor   Sensor instance
 * @param[out] reading  Sensor reading with value and quality
 *
 * @return RESULT_OK on success
 * @return RESULT_ERROR_TIMEOUT if sensor read timed out
 * @return RESULT_ERROR_IO if hardware communication failed
 *
 * @note Quality determination:
 *       - GOOD: Fresh, valid, in-range
 *       - UNCERTAIN: Stale or out-of-range but readable
 *       - BAD: Consecutive failures exceed threshold
 *       - NOT_CONNECTED: Hardware not responding
 *
 * @note Failed reads increment consecutive_failures counter.
 *       Successful reads reset the counter.
 */
```

---

### Medium Priority (TUI and Configuration)

#### `src/tui/pages/page_sensors.c`

##### `int page_sensors_render(...)`
**Recommended:**
```c
/**
 * @brief Render the sensor management page.
 *
 * Displays a list of configured sensors with current values,
 * quality indicators, and status. Supports navigation and
 * selection for CRUD operations.
 *
 * @return 0 on success, -1 on render error
 *
 * @note Key bindings:
 *       - ↑/↓: Navigate sensor list
 *       - A/N: Add new sensor
 *       - E: Edit selected sensor
 *       - D: Delete selected sensor
 *       - C: Calibrate selected sensor
 *       - R: Refresh readings
 *
 * @note Color coding:
 *       - Green: QUALITY_GOOD
 *       - Yellow: QUALITY_UNCERTAIN
 *       - Red: QUALITY_BAD or alarm
 *       - Grey: QUALITY_NOT_CONNECTED
 */
```

#### `src/config/config_manager.c`

##### `result_t config_load_file(...)`
**Recommended:**
```c
/**
 * @brief Load configuration from INI file.
 *
 * Parses the configuration file and populates the app_config_t
 * structure. Missing values use defaults. Invalid values generate
 * warnings but do not cause failure.
 *
 * @param[in]  path    Path to configuration file
 * @param[out] config  Configuration structure to populate
 *
 * @return RESULT_OK on success
 * @return RESULT_ERROR_FILE if file not readable
 * @return RESULT_ERROR_PARSE if syntax error
 *
 * @note Search order if path is NULL:
 *       1. /etc/water-treat/water-treat.conf
 *       2. /etc/water-treat.conf
 *       3. ./water-treat.conf
 *
 * @note Unknown sections/keys generate warnings but are ignored.
 */
```

---

## Summary Statistics

| Repository | Critical | High | Medium | Total |
|------------|----------|------|--------|-------|
| Water-Controller | 3 | 8 | 6 | 17 |
| Water-Treat | 4 | 6 | 5 | 15 |
| **Total** | **7** | **14** | **11** | **32** |

## Recommended Documentation Format

### C Functions (Doxygen)
```c
/**
 * @brief One-line summary.
 *
 * Detailed description if needed.
 *
 * @param[in]  input_param   Description
 * @param[out] output_param  Description
 * @param[in,out] both_param Description
 *
 * @return Return value description
 * @return Alternative return values
 *
 * @pre Preconditions
 * @post Postconditions
 *
 * @note Thread safety: SAFE | UNSAFE | LOCK_REQUIRED
 * @note Memory: ALLOCATES | NO_ALLOC | CALLER_FREES
 *
 * @warning Important warnings
 * @safety Safety-critical notes
 *
 * @see Related functions or documentation
 */
```

### Python Functions
```python
def function_name(param1: Type, param2: Type) -> ReturnType:
    """One-line summary.

    Detailed description if needed.

    Args:
        param1: Description of param1.
        param2: Description of param2.

    Returns:
        Description of return value.

    Raises:
        ExceptionType: When this exception is raised.

    Example:
        >>> function_name(value1, value2)
        expected_result

    Note:
        Additional notes.
    """
```

---

*Generated: 2024-12-22*
*Based on codebase analysis from documentation audit*
