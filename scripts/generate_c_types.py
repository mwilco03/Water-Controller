#!/usr/bin/env python3
"""
Generate C header files from JSON Schema YAML files.

This script reads schemas from schemas/config/*.schema.yaml and generates
C header files with proper types, defines, and documentation.

Usage:
    python scripts/generate_c_types.py

Output:
    src/generated/config_types.h
    src/generated/config_defaults.h
"""

import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML not installed. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


SCHEMA_DIR = Path(__file__).parent.parent / "schemas" / "config"
OUTPUT_DIR = Path(__file__).parent.parent / "src" / "generated"

HEADER_TEMPLATE = """/*
 * AUTO-GENERATED FILE - DO NOT EDIT MANUALLY
 *
 * Generated from: schemas/config/*.schema.yaml
 * Generated at: {timestamp}
 * Generator: scripts/generate_c_types.py
 *
 * To update this file, modify the source schemas and run:
 *   python scripts/generate_c_types.py
 */

#ifndef WTC_GENERATED_{guard}_H
#define WTC_GENERATED_{guard}_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {{
#endif

"""

FOOTER_TEMPLATE = """
#ifdef __cplusplus
}}
#endif

#endif /* WTC_GENERATED_{guard}_H */
"""


def load_schema(path: Path) -> Dict[str, Any]:
    """Load a YAML schema file."""
    with open(path, "r") as f:
        return yaml.safe_load(f)


def to_c_identifier(name: str) -> str:
    """Convert a name to a valid C identifier."""
    # Replace dots and hyphens with underscores
    name = re.sub(r'[.\-]', '_', name)
    # Remove any other invalid characters
    name = re.sub(r'[^a-zA-Z0-9_]', '', name)
    return name


def to_upper_snake(name: str) -> str:
    """Convert to UPPER_SNAKE_CASE."""
    # Insert underscore before uppercase letters
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).upper()


def json_type_to_c(prop: Dict[str, Any], name: str) -> Tuple[str, Optional[int]]:
    """Convert JSON Schema type to C type. Returns (type, array_size).

    For integers, we only optimize to smaller types when BOTH minimum and
    maximum constraints are explicitly specified. Without explicit bounds,
    we default to int32_t (signed) or uint32_t (unsigned based on minimum >= 0).
    """
    prop_type = prop.get("type", "")

    if prop_type == "boolean":
        return "bool", None

    if prop_type == "integer":
        minimum = prop.get("minimum")
        maximum = prop.get("maximum")
        has_bounds = minimum is not None and maximum is not None

        # Default to safe 32-bit types when bounds are not fully specified
        if not has_bounds:
            # If only minimum is specified and it's >= 0, use unsigned
            if minimum is not None and minimum >= 0:
                return "uint32_t", None
            # Otherwise default to signed 32-bit
            return "int32_t", None

        # Both bounds specified - choose smallest type that fits
        if minimum >= 0:
            # Unsigned types
            if maximum <= 255:
                return "uint8_t", None
            elif maximum <= 65535:
                return "uint16_t", None
            elif maximum <= 4294967295:
                return "uint32_t", None
            else:
                return "uint64_t", None
        else:
            # Signed types
            if minimum >= -128 and maximum <= 127:
                return "int8_t", None
            elif minimum >= -32768 and maximum <= 32767:
                return "int16_t", None
            elif minimum >= -2147483648 and maximum <= 2147483647:
                return "int32_t", None
            else:
                return "int64_t", None

    if prop_type == "number":
        return "float", None

    if prop_type == "string":
        max_len = prop.get("maxLength", 256)
        return "char", max_len

    if prop_type == "array":
        # Complex arrays not directly supported
        return "void*", None

    if prop_type == "object":
        return f"{to_c_identifier(name)}_config_t", None

    return "void*", None


def generate_enum(name: str, values: List[str], prefix: str = "") -> str:
    """Generate C enum from JSON Schema enum."""
    lines = []
    enum_name = f"{prefix}{to_upper_snake(name)}"

    lines.append(f"/** {name} enumeration */")
    lines.append(f"typedef enum {{")

    for i, val in enumerate(values):
        enum_val = f"{enum_name}_{to_upper_snake(str(val))}"
        if i == 0:
            lines.append(f"    {enum_val} = 0,")
        else:
            lines.append(f"    {enum_val},")

    lines.append(f"}} {to_c_identifier(name)}_t;")
    lines.append("")

    return "\n".join(lines)


def generate_struct(name: str, properties: Dict[str, Any], prefix: str = "") -> str:
    """Generate C struct from JSON Schema object."""
    lines = []
    nested_structs = []
    enums = []

    struct_name = f"{prefix}{to_c_identifier(name)}_config"

    # First, generate any nested types
    for prop_name, prop in properties.items():
        if prop.get("type") == "object" and "properties" in prop:
            nested = generate_struct(prop_name, prop["properties"], f"{prefix}{to_c_identifier(name)}_")
            nested_structs.append(nested)

        if "enum" in prop and prop.get("type") == "string":
            enum = generate_enum(prop_name, prop["enum"], f"{prefix.upper()}{to_upper_snake(name)}_")
            enums.append(enum)

    # Add nested structs and enums first
    for enum in enums:
        lines.append(enum)

    for nested in nested_structs:
        lines.append(nested)

    # Generate the main struct
    lines.append(f"/**")
    lines.append(f" * {name} configuration")
    if properties:
        desc = next(iter(properties.values())).get("description", "")
        if desc:
            lines.append(f" * {desc[:60]}...")
    lines.append(f" */")
    lines.append(f"typedef struct {{")

    for prop_name, prop in sorted(properties.items()):
        c_type, array_size = json_type_to_c(prop, prop_name)
        c_name = to_c_identifier(prop_name)

        # Add field comment
        desc = prop.get("description", "")
        if desc:
            lines.append(f"    /** {desc[:70]} */")

        # Handle string arrays
        if array_size:
            lines.append(f"    {c_type} {c_name}[{array_size}];")
        # Handle nested objects
        elif prop.get("type") == "object" and "properties" in prop:
            nested_type = f"{prefix}{to_c_identifier(name)}_{to_c_identifier(prop_name)}_config_t"
            lines.append(f"    {nested_type} {c_name};")
        # Handle enums
        elif "enum" in prop and prop.get("type") == "string":
            enum_type = f"{to_c_identifier(prop_name)}_t"
            lines.append(f"    {enum_type} {c_name};")
        else:
            lines.append(f"    {c_type} {c_name};")

    lines.append(f"}} {struct_name}_t;")
    lines.append("")

    return "\n".join(lines)


def generate_defines(schemas: List[Dict[str, Any]]) -> str:
    """Generate #define constants from schemas."""
    lines = []
    lines.append("/* Configuration limits and constants */")
    lines.append("")

    def extract_defines(props: Dict[str, Any], prefix: str = ""):
        for name, prop in props.items():
            if "x-c-define" in prop:
                define_name = prop["x-c-define"]
                default = prop.get("default", 0)
                desc = prop.get("description", "")

                if desc:
                    lines.append(f"/** {desc} */")
                lines.append(f"#define {define_name} {default}")
                lines.append("")

            if prop.get("type") == "object" and "properties" in prop:
                extract_defines(prop["properties"], f"{prefix}{name}_")

    for schema in schemas:
        if "properties" in schema:
            extract_defines(schema["properties"])

    return "\n".join(lines)


def generate_defaults_header(schemas: List[Dict[str, Any]], timestamp: str) -> str:
    """Generate defaults header file."""
    output = HEADER_TEMPLATE.format(timestamp=timestamp, guard="CONFIG_DEFAULTS")

    output += "/* Default configuration values */\n\n"

    def generate_defaults(props: Dict[str, Any], prefix: str = ""):
        lines = []
        for name, prop in sorted(props.items()):
            if prop.get("type") == "object" and "properties" in prop:
                lines.extend(generate_defaults(prop["properties"], f"{prefix}{to_upper_snake(name)}_"))
            elif "default" in prop:
                default = prop["default"]
                define_name = f"WTC_DEFAULT_{prefix}{to_upper_snake(name)}"

                if isinstance(default, bool):
                    lines.append(f"#define {define_name} {'true' if default else 'false'}")
                elif isinstance(default, str):
                    lines.append(f'#define {define_name} "{default}"')
                elif isinstance(default, (int, float)):
                    lines.append(f"#define {define_name} {default}")
        return lines

    for schema in schemas:
        schema_id = schema.get("$id", "").split("/")[-1]
        output += f"/* {schema.get('title', schema_id)} defaults */\n"

        if "properties" in schema:
            prefix = to_upper_snake(schema_id.replace(".schema", "")) + "_"
            defaults = generate_defaults(schema["properties"], prefix)
            output += "\n".join(defaults)
            output += "\n\n"

    output += FOOTER_TEMPLATE.format(guard="CONFIG_DEFAULTS")
    return output


def main():
    """Generate C headers from schemas."""
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
        schemas.append(load_schema(sf))

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Generate types header
    types_output = HEADER_TEMPLATE.format(timestamp=timestamp, guard="CONFIG_TYPES")
    types_output += generate_defines(schemas)
    types_output += "\n"

    for schema in schemas:
        schema_id = schema.get("$id", "").split("/")[-1]
        types_output += f"/* ========== {schema.get('title', schema_id)} ========== */\n\n"

        if "properties" in schema:
            prefix = to_c_identifier(schema_id.replace(".schema", "")) + "_"
            types_output += generate_struct(
                schema_id.replace(".schema", ""),
                schema["properties"],
                ""
            )
            types_output += "\n"

    types_output += FOOTER_TEMPLATE.format(guard="CONFIG_TYPES")

    # Write types header
    types_file = OUTPUT_DIR / "config_types.h"
    with open(types_file, "w") as f:
        f.write(types_output)
    print(f"Generated: {types_file}")

    # Generate defaults header
    defaults_output = generate_defaults_header(schemas, timestamp)
    defaults_file = OUTPUT_DIR / "config_defaults.h"
    with open(defaults_file, "w") as f:
        f.write(defaults_output)
    print(f"Generated: {defaults_file}")

    print(f"\nSchemas processed: {len(schemas)}")


if __name__ == "__main__":
    main()
