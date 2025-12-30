# Contributing to Water-Controller

Thank you for your interest in contributing to the Water Treatment Controller project. This document provides guidelines for contributing code, documentation, and bug reports.

## Code of Conduct

This is critical infrastructure software for water treatment facilities. Contributions must prioritize:

1. **Safety** - Code must fail safely and never compromise treatment processes
2. **Reliability** - Industrial systems require high uptime and predictable behavior
3. **Standards Compliance** - Follow ISA-18.2, PROFINET, and OPC UA standards

## Getting Started

### Development Environment

```bash
# Clone the repository
git clone https://github.com/mwilco03/Water-Controller.git
cd Water-Controller

# Install development dependencies
sudo apt install build-essential cmake pkg-config \
    libpq-dev libjson-c-dev python3-dev python3-venv nodejs npm

# Build the project
mkdir build && cd build
cmake -DCMAKE_BUILD_TYPE=Debug ..
make -j$(nproc)

# Run tests
make test
```

### Project Structure

```
Water-Controller/
├── src/           # C source code (controller, PROFINET, Modbus)
├── web/api/       # Python FastAPI backend
├── web/ui/        # React/Next.js frontend
├── scripts/       # Installation and management scripts
├── tests/         # Unit and integration tests
├── docs/          # Documentation
└── systemd/       # Service unit files
```

## Contribution Workflow

### 1. Create an Issue

Before starting work, create or find an existing issue that describes the change. This helps avoid duplicate work and ensures alignment with project goals.

### 2. Fork and Branch

```bash
# Fork via GitHub, then:
git clone https://github.com/YOUR_USERNAME/Water-Controller.git
cd Water-Controller

# Create a feature branch
git checkout -b feature/your-feature-name

# Or for bug fixes
git checkout -b fix/issue-number-description
```

### 3. Make Changes

Follow the coding standards below when making changes.

### 4. Test Your Changes

```bash
# Build and run tests
cd build
cmake ..
make -j$(nproc)
make test

# For Python changes
cd web/api
python -m pytest

# For frontend changes
cd web/ui
npm test
npm run lint
```

### 5. Submit a Pull Request

- Provide a clear description of the changes
- Reference any related issues
- Ensure all tests pass
- Request review from maintainers

## Coding Standards

### C Code

- Follow C11 standard
- Use `snake_case` for functions and variables
- Use `UPPER_CASE` for constants and macros
- Include header guards in all `.h` files
- Document public functions with Doxygen-style comments

```c
/**
 * @brief Start the PROFINET controller
 * @param interface Network interface name (e.g., "eth0")
 * @param cycle_time_ms Cycle time in milliseconds
 * @return 0 on success, negative error code on failure
 */
int profinet_controller_start(const char *interface, int cycle_time_ms);
```

### Python Code

- Follow PEP 8 style guide
- Use type hints for function signatures
- Use `black` for formatting
- Use `mypy` for type checking

```python
async def get_rtu_sensors(station_name: str) -> list[SensorReading]:
    """Retrieve all sensor readings from an RTU.

    Args:
        station_name: The RTU station name

    Returns:
        List of sensor readings with quality codes
    """
    ...
```

### TypeScript/React Code

- Use TypeScript strict mode
- Follow ESLint configuration
- Use functional components with hooks
- Avoid `any` type

```typescript
interface SensorDisplayProps {
  stationName: string;
  slotId: number;
  refreshInterval?: number;
}

export const SensorDisplay: React.FC<SensorDisplayProps> = ({
  stationName,
  slotId,
  refreshInterval = 1000,
}) => {
  // Component implementation
};
```

### Commit Messages

Use clear, descriptive commit messages:

```
feat: Add Modbus RTU serial support

- Implement serial port configuration
- Add parity and stop bit options
- Include RS-485 direction control

Closes #42
```

Prefixes:
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation only
- `refactor:` - Code refactoring
- `test:` - Adding or updating tests
- `chore:` - Build process or auxiliary tools

## Testing Requirements

### Unit Tests

All new code should include unit tests:

- C code: Use the project's test framework in `tests/`
- Python: Use `pytest` with fixtures
- TypeScript: Use Jest and React Testing Library

### Integration Tests

For changes affecting multiple components:

- Test PROFINET communication with mock RTUs
- Test API endpoints with realistic payloads
- Test frontend components with API mocking

### Documentation Tests

Verify documentation accuracy:

- Code examples should be tested
- API endpoints should match OpenAPI spec
- Installation steps should be validated

## Security Considerations

This is industrial control system software. Security is critical:

- Never commit credentials or secrets
- Validate all external input
- Use parameterized queries for database access
- Follow the principle of least privilege
- Report security vulnerabilities privately (do not create public issues)

## Documentation

- Update relevant documentation when changing functionality
- Keep API documentation in sync with code
- Add inline comments for complex logic
- Update CHANGELOG.md for user-visible changes

## Need Help?

- Check existing [documentation](docs/README.md)
- Search [existing issues](https://github.com/mwilco03/Water-Controller/issues)
- Open a new issue for questions

## License

By contributing, you agree that your contributions will be licensed under the GPL-3.0-or-later license.
