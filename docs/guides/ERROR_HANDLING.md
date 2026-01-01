# Error Handling Patterns

This document defines the error handling patterns used across all components of the Water Treatment Controller system.

## Overview

The system uses consistent error handling patterns across:
- **C Controller**: Error codes and logging
- **Python API**: Exception hierarchy and HTTP error responses
- **React UI**: Error boundaries and user-facing messages

## Error Categories

| Category | Code Range | Description |
|----------|-----------|-------------|
| Success | 0 | Operation completed successfully |
| Validation | 100-199 | Input validation failures |
| Communication | 200-299 | Network/protocol errors |
| Hardware | 300-399 | Device/sensor failures |
| Configuration | 400-499 | Config parsing/loading errors |
| Internal | 500-599 | Unexpected internal errors |

## C Controller Error Handling

### Error Code Structure

```c
// include/error_codes.h
typedef enum {
    WTC_OK = 0,

    // Validation errors (100-199)
    WTC_ERR_INVALID_PARAM = 100,
    WTC_ERR_OUT_OF_RANGE = 101,
    WTC_ERR_NULL_POINTER = 102,

    // Communication errors (200-299)
    WTC_ERR_CONNECTION_FAILED = 200,
    WTC_ERR_TIMEOUT = 201,
    WTC_ERR_PROFINET_ERROR = 210,
    WTC_ERR_MODBUS_ERROR = 220,

    // Hardware errors (300-399)
    WTC_ERR_SENSOR_FAULT = 300,
    WTC_ERR_ACTUATOR_FAULT = 310,
    WTC_ERR_RTU_OFFLINE = 320,

    // Configuration errors (400-499)
    WTC_ERR_CONFIG_PARSE = 400,
    WTC_ERR_CONFIG_MISSING = 401,
    WTC_ERR_CONFIG_INVALID = 402,

    // Internal errors (500-599)
    WTC_ERR_MEMORY = 500,
    WTC_ERR_INTERNAL = 501
} wtc_error_t;
```

### Error Handling Pattern

```c
wtc_error_t result = some_operation();
if (result != WTC_OK) {
    wtc_log_error("Operation failed: %s", wtc_error_string(result));
    // Handle or propagate error
    return result;
}
```

### Logging Levels

| Level | Usage |
|-------|-------|
| ERROR | Failures requiring attention |
| WARNING | Recoverable issues |
| INFO | Normal operation events |
| DEBUG | Detailed debugging info |

## Python API Error Handling

### Exception Hierarchy

```python
# app/core/exceptions.py
class WTCException(Exception):
    """Base exception for all WTC errors."""
    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"

class ValidationError(WTCException):
    """Input validation failure."""
    status_code = 400
    error_code = "VALIDATION_ERROR"

class NotFoundError(WTCException):
    """Resource not found."""
    status_code = 404
    error_code = "NOT_FOUND"

class CommunicationError(WTCException):
    """Communication failure with device."""
    status_code = 502
    error_code = "COMMUNICATION_ERROR"

class ConfigurationError(WTCException):
    """Configuration error."""
    status_code = 500
    error_code = "CONFIGURATION_ERROR"
```

### API Error Response Format

All API errors return a consistent JSON structure:

```json
{
    "error": {
        "code": "VALIDATION_ERROR",
        "message": "Human-readable error message",
        "details": {
            "field": "ph_value",
            "constraint": "must be between 0 and 14"
        },
        "request_id": "uuid-for-tracking"
    }
}
```

### HTTP Status Code Usage

| Code | Usage |
|------|-------|
| 200 | Success |
| 201 | Resource created |
| 204 | Success, no content |
| 400 | Validation error |
| 401 | Authentication required |
| 403 | Permission denied |
| 404 | Resource not found |
| 409 | Conflict (e.g., duplicate) |
| 422 | Unprocessable entity |
| 500 | Internal server error |
| 502 | Upstream error (device communication) |
| 503 | Service unavailable |

### Exception Handler Pattern

```python
from fastapi import Request
from fastapi.responses import JSONResponse

@app.exception_handler(WTCException)
async def wtc_exception_handler(request: Request, exc: WTCException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.error_code,
                "message": str(exc),
                "details": exc.details if hasattr(exc, 'details') else None,
                "request_id": request.state.request_id
            }
        }
    )
```

## React UI Error Handling

### Error Boundary Pattern

```tsx
// components/ErrorBoundary.tsx
class ErrorBoundary extends React.Component<Props, State> {
    static getDerivedStateFromError(error: Error) {
        return { hasError: true, error };
    }

    componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
        // Log to monitoring service
        logger.error('UI Error', { error, errorInfo });
    }

    render() {
        if (this.state.hasError) {
            return <ErrorFallback error={this.state.error} />;
        }
        return this.props.children;
    }
}
```

### API Error Handling

```typescript
// lib/api.ts
async function fetchWithErrorHandling<T>(url: string): Promise<T> {
    try {
        const response = await fetch(url);

        if (!response.ok) {
            const error = await response.json();
            throw new APIError(error.error.code, error.error.message);
        }

        return response.json();
    } catch (error) {
        if (error instanceof APIError) {
            throw error;
        }
        // Network or parsing error
        throw new APIError('NETWORK_ERROR', 'Failed to connect to server');
    }
}
```

### User-Facing Error Messages

| Error Code | User Message |
|------------|--------------|
| VALIDATION_ERROR | "Please check your input and try again" |
| NOT_FOUND | "The requested item was not found" |
| COMMUNICATION_ERROR | "Unable to communicate with device. Check connection." |
| NETWORK_ERROR | "Network error. Please check your connection." |
| INTERNAL_ERROR | "An unexpected error occurred. Please try again." |

## Cross-Component Error Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   React UI  │────▶│  FastAPI    │────▶│ C Controller│
└─────────────┘     └─────────────┘     └─────────────┘
      ▲                   ▲                   │
      │                   │                   │
      │    JSON Error     │   wtc_error_t     │
      │◀──────────────────│◀──────────────────│
```

1. **C Controller** returns `wtc_error_t` code
2. **Python API** maps error code to exception and HTTP response
3. **React UI** displays user-friendly message

## Error Logging Standards

### Log Format

```
[TIMESTAMP] [LEVEL] [COMPONENT] [REQUEST_ID] Message {context}
```

Example:
```
2024-01-15T10:30:45Z ERROR api abc123 Failed to read sensor {"rtu": "rtu-tank-1", "slot": 1, "error": "TIMEOUT"}
```

### Required Context

All error logs must include:
- Timestamp (ISO 8601)
- Log level
- Component identifier
- Request/correlation ID (when applicable)
- Error code or type
- Relevant context (IDs, values)

## Recovery Patterns

### Retry with Backoff

```python
async def retry_with_backoff(func, max_retries=3, base_delay=1.0):
    for attempt in range(max_retries):
        try:
            return await func()
        except CommunicationError:
            if attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            await asyncio.sleep(delay)
```

### Circuit Breaker

For repeated failures, use circuit breaker pattern to prevent cascade:

```python
class CircuitBreaker:
    def __init__(self, threshold=5, timeout=60):
        self.failure_count = 0
        self.threshold = threshold
        self.timeout = timeout
        self.last_failure = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
```

## Testing Error Handling

### Unit Tests

```python
def test_validation_error_response():
    response = client.post("/api/v1/sensors", json={"invalid": "data"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
```

### Integration Tests

```python
def test_device_communication_error():
    # Simulate device offline
    with mock_device_offline():
        response = client.get("/api/v1/rtus/1/status")
        assert response.status_code == 502
        assert response.json()["error"]["code"] == "COMMUNICATION_ERROR"
```
