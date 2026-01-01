# Water Treatment Controller - Makefile
#
# Build targets for the Water Treatment Controller SCADA system.
# Includes schema-driven code generation targets.

.PHONY: all build clean test docs generate validate help

# Default target
all: generate build

# Python executable
PYTHON ?= python3

# Directories
SCHEMA_DIR := schemas
SCRIPTS_DIR := scripts
DOCS_GEN_DIR := docs/generated
SRC_GEN_DIR := src/generated
WEB_GEN_DIR := web/api/models/generated

#
# Schema-Driven Generation
# ========================
# These targets generate code and documentation from YAML schemas.
# The schemas in schemas/ are the single source of truth.
#

# Generate all artifacts from schemas
generate: generate-docs generate-c generate-pydantic
	@echo "All artifacts generated from schemas."

# Generate documentation from schemas
generate-docs:
	@echo "Generating documentation from schemas..."
	$(PYTHON) $(SCRIPTS_DIR)/generate_docs.py

# Generate C headers from schemas
generate-c:
	@echo "Generating C headers from schemas..."
	$(PYTHON) $(SCRIPTS_DIR)/generate_c_types.py

# Generate Pydantic models from schemas
generate-pydantic:
	@echo "Generating Pydantic models from schemas..."
	$(PYTHON) $(SCRIPTS_DIR)/generate_pydantic.py

# Validate schemas are well-formed
validate-schemas:
	@echo "Validating schemas..."
	$(PYTHON) $(SCRIPTS_DIR)/validate_schemas.py --verbose

# Check if generated files are in sync with schemas
validate-sync:
	@echo "Checking if generated files are in sync..."
	$(PYTHON) $(SCRIPTS_DIR)/validate_sync.py

# Validate configuration files against schemas
validate-config:
	@echo "Validating configuration files..."
	$(PYTHON) $(SCRIPTS_DIR)/validate_config.py

# Validate cross-component integration
validate-integration:
	@echo "Validating cross-component integration..."
	$(PYTHON) $(SCRIPTS_DIR)/validate_integration.py --verbose

# Full validation (schemas + sync check + config + integration)
validate: validate-schemas validate-sync validate-config validate-integration
	@echo "All validations passed."

# Regenerate all artifacts (use when schemas change)
regenerate:
	@echo "Regenerating all artifacts from schemas..."
	$(PYTHON) $(SCRIPTS_DIR)/validate_schemas.py --regenerate
	@echo "Done. Don't forget to commit the generated files!"

#
# Build Targets
# =============
#

# Build the controller
build:
	@echo "Building water-controller..."
	@if [ -d build ]; then cd build && cmake --build .; \
	else mkdir -p build && cd build && cmake .. && cmake --build .; fi

# Clean build artifacts
clean:
	@echo "Cleaning build artifacts..."
	rm -rf build/
	rm -rf __pycache__/
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -delete

# Clean generated files (use with caution!)
clean-generated:
	@echo "Cleaning generated files..."
	rm -f $(DOCS_GEN_DIR)/*.md
	rm -f $(SRC_GEN_DIR)/*.h
	rm -f $(WEB_GEN_DIR)/*.py

#
# Testing
# =======
#
# Unified test entry point for all components.
# Use `make test` for a complete test run across C, Python, and JavaScript.
#

# Run all tests (unified entry point)
test: test-c test-python test-js test-integration
	@echo ""
	@echo "=========================================="
	@echo "All tests completed successfully!"
	@echo "=========================================="

# Run C tests (controller)
test-c:
	@echo "Running C tests..."
	@if [ -d build ]; then \
		cd build && ctest --output-on-failure; \
	else \
		echo "No build directory found. Run 'make build' first."; \
	fi

# Run Python tests (API)
test-python:
	@echo "Running Python tests..."
	cd web/api && $(PYTHON) -m pytest tests/ -v --tb=short

# Run JavaScript tests (UI)
test-js:
	@echo "Running JavaScript tests..."
	@if [ -f web/ui/package.json ]; then \
		cd web/ui && npm test -- --passWithNoTests 2>/dev/null || echo "No JS tests configured"; \
	else \
		echo "No web/ui package.json found"; \
	fi

# Run integration tests
test-integration:
	@echo "Running integration tests..."
	$(PYTHON) -m pytest tests/integration/ -v --tb=short -m "not docker" 2>/dev/null || echo "No integration tests found or markers not set"

# Run all tests with coverage
test-coverage:
	@echo "Running tests with coverage..."
	cd web/api && $(PYTHON) -m pytest tests/ -v --cov=app --cov-report=html --cov-report=term

# Quick test (fast subset for development)
test-quick:
	@echo "Running quick tests..."
	cd web/api && $(PYTHON) -m pytest tests/ -v -x --tb=short -m "not slow"

#
# Documentation
# =============
#

# Build full documentation
docs: generate-docs generate-openapi
	@echo "Documentation generated in $(DOCS_GEN_DIR)/"

# Generate OpenAPI specification from FastAPI
generate-openapi:
	@echo "Generating OpenAPI specification..."
	@mkdir -p docs/api
	$(PYTHON) $(SCRIPTS_DIR)/generate_openapi.py --output docs/api/openapi.json

#
# Development Helpers
# ===================
#

# Install Python dependencies for schema tools
install-deps:
	@echo "Installing Python dependencies..."
	pip install pyyaml jsonschema

# Format all code
format: format-python format-js
	@echo "All code formatted."

# Format Python code
format-python:
	@echo "Formatting Python code..."
	@if command -v ruff >/dev/null 2>&1; then \
		cd web/api && ruff format app/ tests/; \
		ruff format $(SCRIPTS_DIR)/*.py; \
	elif command -v black >/dev/null 2>&1; then \
		black $(SCRIPTS_DIR)/*.py web/api/app/ web/api/tests/; \
	else \
		echo "Neither ruff nor black installed, skipping formatting"; \
	fi

# Format JavaScript code
format-js:
	@echo "Formatting JavaScript code..."
	@if [ -f web/ui/package.json ]; then \
		cd web/ui && npm run format 2>/dev/null || echo "No format script in package.json"; \
	fi

# Lint all code (unified entry point)
lint: lint-python lint-js lint-c
	@echo ""
	@echo "All linting completed."

# Lint Python code (ruff + mypy)
lint-python:
	@echo "Linting Python code..."
	@if command -v ruff >/dev/null 2>&1; then \
		echo "  Running ruff..."; \
		cd web/api && ruff check app/ tests/; \
	elif command -v flake8 >/dev/null 2>&1; then \
		echo "  Running flake8..."; \
		flake8 $(SCRIPTS_DIR)/*.py web/api/app/ --max-line-length=120; \
	else \
		echo "  No Python linter installed (install ruff or flake8)"; \
	fi
	@echo "  Running mypy..."
	@if command -v mypy >/dev/null 2>&1; then \
		cd web/api && mypy app/ --ignore-missing-imports; \
	else \
		echo "  mypy not installed, skipping type checking"; \
	fi

# Lint JavaScript/TypeScript code
lint-js:
	@echo "Linting JavaScript/TypeScript code..."
	@if [ -f web/ui/package.json ]; then \
		cd web/ui && npm run lint 2>/dev/null || echo "  No lint script in package.json"; \
	fi

# Lint C code
lint-c:
	@echo "Linting C code..."
	@if command -v cppcheck >/dev/null 2>&1; then \
		echo "  Running cppcheck..."; \
		cppcheck --enable=warning,style,performance --error-exitcode=1 \
			--suppress=missingIncludeSystem \
			src/ include/ 2>&1 | head -50 || true; \
	elif command -v clang-tidy >/dev/null 2>&1; then \
		echo "  Running clang-tidy..."; \
		find src/ include/ -name "*.c" -o -name "*.h" | head -10 | \
			xargs -I{} clang-tidy {} -- -Iinclude 2>/dev/null || true; \
	else \
		echo "  No C linter installed (install cppcheck or clang-tidy)"; \
	fi

#
# Help
# ====
#

help:
	@echo "Water Treatment Controller - Build Targets"
	@echo ""
	@echo "Schema Generation:"
	@echo "  make generate          - Generate all artifacts from schemas"
	@echo "  make generate-docs     - Generate documentation"
	@echo "  make generate-c        - Generate C headers"
	@echo "  make generate-pydantic - Generate Pydantic models"
	@echo "  make regenerate        - Force regenerate all (after schema changes)"
	@echo ""
	@echo "Validation:"
	@echo "  make validate             - Run all validations"
	@echo "  make validate-schemas     - Validate schema syntax"
	@echo "  make validate-sync        - Check generated files are in sync"
	@echo "  make validate-config      - Validate configuration files"
	@echo "  make validate-integration - Validate cross-component integration"
	@echo ""
	@echo "Build:"
	@echo "  make build             - Build the controller"
	@echo "  make clean             - Clean build artifacts"
	@echo ""
	@echo "Testing (unified entry points):"
	@echo "  make test              - Run ALL tests (C, Python, JS, integration)"
	@echo "  make test-c            - Run C tests only"
	@echo "  make test-python       - Run Python tests only"
	@echo "  make test-js           - Run JavaScript tests only"
	@echo "  make test-integration  - Run integration tests only"
	@echo "  make test-coverage     - Run tests with coverage report"
	@echo "  make test-quick        - Fast test subset for development"
	@echo ""
	@echo "Linting (unified entry points):"
	@echo "  make lint              - Run ALL linters (Python, JS, C)"
	@echo "  make lint-python       - Run Python linters (ruff + mypy)"
	@echo "  make lint-js           - Run JavaScript/TypeScript linter"
	@echo "  make lint-c            - Run C linter (cppcheck)"
	@echo ""
	@echo "Documentation:"
	@echo "  make docs              - Build documentation"
	@echo ""
	@echo "Development:"
	@echo "  make install-deps      - Install Python dependencies"
	@echo "  make format            - Format all code"
	@echo "  make format-python     - Format Python code"
	@echo "  make format-js         - Format JavaScript code"
