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

# Full validation (schemas + sync check)
validate: validate-schemas validate-sync
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

# Run all tests
test:
	@echo "Running tests..."
	@if [ -d build ]; then cd build && ctest --output-on-failure; fi

# Run Python tests
test-python:
	@echo "Running Python tests..."
	$(PYTHON) -m pytest tests/ -v

#
# Documentation
# =============
#

# Build full documentation
docs: generate-docs
	@echo "Documentation generated in $(DOCS_GEN_DIR)/"

#
# Development Helpers
# ===================
#

# Install Python dependencies for schema tools
install-deps:
	@echo "Installing Python dependencies..."
	pip install pyyaml jsonschema

# Format Python code
format:
	@echo "Formatting Python code..."
	@if command -v black >/dev/null 2>&1; then \
		black $(SCRIPTS_DIR)/*.py; \
	else \
		echo "black not installed, skipping formatting"; \
	fi

# Lint Python code
lint:
	@echo "Linting Python code..."
	@if command -v flake8 >/dev/null 2>&1; then \
		flake8 $(SCRIPTS_DIR)/*.py --max-line-length=100; \
	else \
		echo "flake8 not installed, skipping lint"; \
	fi

#
# Help
# ====
#

help:
	@echo "Water Treatment Controller - Build Targets"
	@echo ""
	@echo "Schema Generation:"
	@echo "  make generate       - Generate all artifacts from schemas"
	@echo "  make generate-docs  - Generate documentation"
	@echo "  make generate-c     - Generate C headers"
	@echo "  make generate-pydantic - Generate Pydantic models"
	@echo "  make regenerate     - Force regenerate all (after schema changes)"
	@echo ""
	@echo "Validation:"
	@echo "  make validate       - Run all validations"
	@echo "  make validate-schemas - Validate schema syntax"
	@echo "  make validate-sync  - Check generated files are in sync"
	@echo ""
	@echo "Build:"
	@echo "  make build          - Build the controller"
	@echo "  make clean          - Clean build artifacts"
	@echo "  make test           - Run tests"
	@echo ""
	@echo "Documentation:"
	@echo "  make docs           - Build documentation"
	@echo ""
	@echo "Development:"
	@echo "  make install-deps   - Install Python dependencies"
	@echo "  make format         - Format Python code"
	@echo "  make lint           - Lint Python code"
