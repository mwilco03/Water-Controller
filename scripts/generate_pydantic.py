#!/usr/bin/env python3
"""
Generate Pydantic models from JSON Schema YAML files.

This script reads schemas from schemas/config/*.schema.yaml and generates
Pydantic v2 models for Python type validation.

Usage:
    python scripts/generate_pydantic.py

Output:
    web/api/models/generated/config_models.py
"""

import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML not installed. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


SCHEMA_DIR = Path(__file__).parent.parent / "schemas" / "config"
OUTPUT_DIR = Path(__file__).parent.parent / "web" / "api" / "models" / "generated"

HEADER = '''"""
AUTO-GENERATED FILE - DO NOT EDIT MANUALLY

Generated from: schemas/config/*.schema.yaml
Generated at: {timestamp}
Generator: scripts/generate_pydantic.py

To update this file, modify the source schemas and run:
    python scripts/generate_pydantic.py
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator


'''


def load_schema(path: Path) -> Dict[str, Any]:
    """Load a YAML schema file."""
    with open(path, "r") as f:
        return yaml.safe_load(f)


def to_pascal_case(name: str) -> str:
    """Convert to PascalCase."""
    # Replace dots, hyphens, underscores with spaces, then title case
    name = re.sub(r'[.\-_]', ' ', name)
    return ''.join(word.capitalize() for word in name.split())


def to_snake_case(name: str) -> str:
    """Convert to snake_case."""
    # Insert underscore before uppercase letters
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    s2 = re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1)
    # Replace dots and hyphens
    s3 = re.sub(r'[.\-]', '_', s2)
    return s3.lower()


def json_type_to_python(prop: Dict[str, Any], name: str) -> str:
    """Convert JSON Schema type to Python type hint."""
    prop_type = prop.get("type", "")

    if "enum" in prop:
        return to_pascal_case(name) + "Enum"

    if prop_type == "boolean":
        return "bool"

    if prop_type == "integer":
        return "int"

    if prop_type == "number":
        return "float"

    if prop_type == "string":
        return "str"

    if prop_type == "array":
        items = prop.get("items", {})
        item_type = json_type_to_python(items, name + "_item")
        return f"List[{item_type}]"

    if prop_type == "object":
        if "properties" in prop:
            return to_pascal_case(name) + "Config"
        return "Dict[str, Any]"

    return "Any"


def generate_enum(name: str, values: List[str]) -> str:
    """Generate Python Enum from JSON Schema enum."""
    lines = []
    enum_name = to_pascal_case(name) + "Enum"

    lines.append(f"class {enum_name}(str, Enum):")
    lines.append(f'    """Enumeration for {name}."""')
    lines.append("")

    for val in values:
        # Create valid Python identifier
        py_name = to_snake_case(str(val)).upper()
        # Handle empty strings and strings starting with digits
        if not py_name:
            py_name = "EMPTY"
        elif py_name[0].isdigit():
            py_name = "_" + py_name
        lines.append(f'    {py_name} = "{val}"')

    lines.append("")
    return "\n".join(lines)


def generate_field(name: str, prop: Dict[str, Any]) -> str:
    """Generate Pydantic Field definition."""
    python_type = json_type_to_python(prop, name)
    field_name = to_snake_case(name)

    field_args = []

    # Default value
    default = prop.get("default")
    if default is None:
        field_args.append("default=None")
        python_type = f"Optional[{python_type}]"
    elif isinstance(default, bool):
        field_args.append(f"default={default}")
    elif isinstance(default, str):
        field_args.append(f'default="{default}"')
    elif isinstance(default, (int, float)):
        field_args.append(f"default={default}")
    elif isinstance(default, list):
        if len(default) == 0:
            field_args.append("default_factory=list")
        else:
            field_args.append(f"default={default}")
    else:
        field_args.append("default=None")
        python_type = f"Optional[{python_type}]"

    # Constraints
    if "minimum" in prop:
        field_args.append(f"ge={prop['minimum']}")
    if "maximum" in prop:
        field_args.append(f"le={prop['maximum']}")
    if "minLength" in prop:
        field_args.append(f"min_length={prop['minLength']}")
    if "maxLength" in prop:
        field_args.append(f"max_length={prop['maxLength']}")
    if "pattern" in prop:
        field_args.append(f'pattern=r"{prop["pattern"]}"')

    # Description
    desc = prop.get("description", "")
    if desc:
        # Escape quotes in description
        desc = desc.replace('"', '\\"')
        field_args.append(f'description="{desc}"')

    # Build field definition
    if field_args:
        return f"    {field_name}: {python_type} = Field({', '.join(field_args)})"
    else:
        return f"    {field_name}: {python_type}"


def generate_model(name: str, schema: Dict[str, Any], collected_enums: Set[str]) -> str:
    """Generate Pydantic model from JSON Schema object."""
    lines = []
    nested_models = []
    enums = []

    properties = schema.get("properties", {})
    class_name = to_pascal_case(name) + "Config"

    # First, collect any nested types
    for prop_name, prop in properties.items():
        if prop.get("type") == "object" and "properties" in prop:
            nested = generate_model(prop_name, prop, collected_enums)
            nested_models.append(nested)

        if "enum" in prop and prop.get("type") == "string":
            enum_name = to_pascal_case(prop_name) + "Enum"
            if enum_name not in collected_enums:
                enum = generate_enum(prop_name, prop["enum"])
                enums.append(enum)
                collected_enums.add(enum_name)

    # Add nested models and enums first (dependencies)
    for enum in enums:
        lines.append(enum)

    for nested in nested_models:
        lines.append(nested)

    # Generate the main model
    desc = schema.get("description", "")

    lines.append(f"class {class_name}(BaseModel):")
    if desc:
        lines.append(f'    """{desc}"""')
    else:
        lines.append(f'    """Configuration for {name}."""')
    lines.append("")

    if not properties:
        lines.append("    pass")
    else:
        for prop_name, prop in sorted(properties.items()):
            lines.append(generate_field(prop_name, prop))

    lines.append("")

    # Add model_config for Pydantic v2
    lines.append("    model_config = {")
    lines.append('        "extra": "forbid",')
    lines.append('        "validate_default": True,')
    lines.append("    }")
    lines.append("")

    return "\n".join(lines)


def main():
    """Generate Pydantic models from schemas."""
    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load all schemas
    schema_files = sorted(SCHEMA_DIR.glob("*.schema.yaml"))

    if not schema_files:
        print(f"ERROR: No schema files found in {SCHEMA_DIR}", file=sys.stderr)
        sys.exit(1)

    schemas = []
    for sf in schema_files:
        print(f"Loading: {sf.name}")
        schemas.append((sf.stem.replace(".schema", ""), load_schema(sf)))

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Generate models
    output = HEADER.format(timestamp=timestamp)

    collected_enums: Set[str] = set()

    for name, schema in schemas:
        output += f"# ========== {schema.get('title', name)} ==========\n\n"
        output += generate_model(name, schema, collected_enums)
        output += "\n"

    # Add a combined config model
    output += "# ========== Combined Configuration ==========\n\n"
    output += "class WaterControllerConfig(BaseModel):\n"
    output += '    """Complete Water Controller configuration."""\n\n'

    for name, schema in schemas:
        field_name = to_snake_case(name)
        class_name = to_pascal_case(name) + "Config"
        desc = schema.get("description", "")
        if desc:
            output += f'    {field_name}: Optional[{class_name}] = Field(default=None, description="{desc}")\n'
        else:
            output += f"    {field_name}: Optional[{class_name}] = None\n"

    output += "\n"
    output += "    model_config = {\n"
    output += '        "extra": "forbid",\n'
    output += '        "validate_default": True,\n'
    output += "    }\n"

    # Write output
    output_file = OUTPUT_DIR / "config_models.py"
    with open(output_file, "w") as f:
        f.write(output)

    # Create __init__.py
    init_file = OUTPUT_DIR / "__init__.py"
    init_content = f'''"""
Auto-generated configuration models.
Generated at: {timestamp}
"""

from .config_models import *
'''
    with open(init_file, "w") as f:
        f.write(init_content)

    print(f"\nGenerated: {output_file}")
    print(f"Generated: {init_file}")
    print(f"Schemas processed: {len(schemas)}")


if __name__ == "__main__":
    main()
