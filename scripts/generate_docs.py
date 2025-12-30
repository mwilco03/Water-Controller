#!/usr/bin/env python3
"""
Generate documentation from JSON Schema YAML files.

This script reads all schemas from schemas/config/*.schema.yaml and generates
comprehensive Markdown documentation in docs/generated/.

Usage:
    python scripts/generate_docs.py

Output:
    docs/generated/CONFIGURATION.md
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML not installed. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


SCHEMA_DIR = Path(__file__).parent.parent / "schemas" / "config"
OUTPUT_DIR = Path(__file__).parent.parent / "docs" / "generated"

HEADER = """<!--
  AUTO-GENERATED FILE - DO NOT EDIT MANUALLY

  Generated from: schemas/config/*.schema.yaml
  Generated at: {timestamp}
  Generator: scripts/generate_docs.py

  To update this file, modify the source schemas and run:
    python scripts/generate_docs.py
-->

# Water Treatment Controller Configuration Reference

This document is automatically generated from the configuration schemas.
It provides a complete reference for all configuration options.

"""


def load_schema(path: Path) -> Dict[str, Any]:
    """Load a YAML schema file."""
    with open(path, "r") as f:
        return yaml.safe_load(f)


def get_type_string(prop: Dict[str, Any]) -> str:
    """Get a human-readable type string."""
    prop_type = prop.get("type", "any")

    if "enum" in prop:
        return f"`{prop_type}` ({', '.join(f'`{v}`' for v in prop['enum'])})"

    if prop_type == "integer":
        constraints = []
        if "minimum" in prop:
            constraints.append(f"min: {prop['minimum']}")
        if "maximum" in prop:
            constraints.append(f"max: {prop['maximum']}")
        if constraints:
            return f"`integer` ({', '.join(constraints)})"
        return "`integer`"

    if prop_type == "number":
        constraints = []
        if "minimum" in prop:
            constraints.append(f"min: {prop['minimum']}")
        if "maximum" in prop:
            constraints.append(f"max: {prop['maximum']}")
        if constraints:
            return f"`number` ({', '.join(constraints)})"
        return "`number`"

    if prop_type == "string":
        if "format" in prop:
            return f"`string` ({prop['format']})"
        if "maxLength" in prop:
            return f"`string` (max {prop['maxLength']} chars)"
        return "`string`"

    if prop_type == "boolean":
        return "`boolean`"

    if prop_type == "array":
        items = prop.get("items", {})
        item_type = items.get("type", "any")
        return f"`array<{item_type}>`"

    if prop_type == "object":
        return "`object`"

    return f"`{prop_type}`"


def get_default_string(prop: Dict[str, Any]) -> str:
    """Get a formatted default value."""
    default = prop.get("default")
    if default is None:
        return "-"
    if isinstance(default, bool):
        return f"`{str(default).lower()}`"
    if isinstance(default, str):
        if default == "":
            return '`""`'
        return f'`"{default}"`'
    if isinstance(default, (int, float)):
        return f"`{default}`"
    if isinstance(default, list):
        if len(default) == 0:
            return "`[]`"
        return f"`[...]` ({len(default)} items)"
    return f"`{default}`"


def format_description(prop: Dict[str, Any], indent: str = "") -> str:
    """Format description with metadata."""
    desc = prop.get("description", "")

    extras = []
    if "x-env-var" in prop:
        extras.append(f"Env: `{prop['x-env-var']}`")
    if "x-cli-arg" in prop:
        extras.append(f"CLI: `{prop['x-cli-arg']}`")
    if "x-unit" in prop:
        extras.append(f"Unit: {prop['x-unit']}")
    if "x-sensitive" in prop and prop["x-sensitive"]:
        extras.append("**SENSITIVE**")
    if "x-readonly" in prop and prop["x-readonly"]:
        extras.append("*read-only*")

    if extras:
        desc = f"{desc} ({', '.join(extras)})"

    return desc


def generate_property_table(properties: Dict[str, Any], prefix: str = "") -> str:
    """Generate a Markdown table for properties."""
    if not properties:
        return ""

    lines = []
    lines.append("| Parameter | Type | Default | Description |")
    lines.append("|-----------|------|---------|-------------|")

    for name, prop in sorted(properties.items()):
        full_name = f"{prefix}{name}" if prefix else name

        if prop.get("type") == "object" and "properties" in prop:
            # Skip nested objects in table, they get their own section
            continue

        type_str = get_type_string(prop)
        default_str = get_default_string(prop)
        desc = format_description(prop)

        # Truncate long descriptions for table
        if len(desc) > 80:
            desc = desc[:77] + "..."

        lines.append(f"| `{full_name}` | {type_str} | {default_str} | {desc} |")

    return "\n".join(lines)


def generate_env_var_reference(schemas: List[Dict[str, Any]]) -> str:
    """Generate environment variable quick reference."""
    env_vars = []

    def extract_env_vars(props: Dict[str, Any], path: str = ""):
        for name, prop in props.items():
            if "x-env-var" in prop:
                env_vars.append({
                    "var": prop["x-env-var"],
                    "default": prop.get("default", ""),
                    "description": prop.get("description", ""),
                    "path": f"{path}{name}" if path else name
                })
            if prop.get("type") == "object" and "properties" in prop:
                extract_env_vars(prop["properties"], f"{path}{name}.")

    for schema in schemas:
        if "properties" in schema:
            extract_env_vars(schema["properties"])

    if not env_vars:
        return ""

    lines = ["## Environment Variable Quick Reference", ""]
    lines.append("| Variable | Default | Description |")
    lines.append("|----------|---------|-------------|")

    for ev in sorted(env_vars, key=lambda x: x["var"]):
        default = ev["default"]
        if isinstance(default, str):
            default = f'`"{default}"`' if default else '`""`'
        elif isinstance(default, bool):
            default = f"`{str(default).lower()}`"
        else:
            default = f"`{default}`"

        desc = ev["description"]
        if len(desc) > 60:
            desc = desc[:57] + "..."

        lines.append(f"| `{ev['var']}` | {default} | {desc} |")

    return "\n".join(lines)


def generate_section(schema: Dict[str, Any], level: int = 2) -> str:
    """Generate documentation section for a schema."""
    lines = []

    title = schema.get("title", "Configuration")
    description = schema.get("description", "")

    lines.append(f"{'#' * level} {title}")
    lines.append("")
    if description:
        lines.append(description)
        lines.append("")

    properties = schema.get("properties", {})

    # Generate table for non-object properties
    table = generate_property_table(properties)
    if table:
        lines.append(table)
        lines.append("")

    # Generate subsections for nested objects
    for name, prop in sorted(properties.items()):
        if prop.get("type") == "object" and "properties" in prop:
            prop_desc = prop.get("description", "")
            lines.append(f"{'#' * (level + 1)} {name}")
            lines.append("")
            if prop_desc:
                lines.append(prop_desc)
                lines.append("")

            nested_table = generate_property_table(prop["properties"], f"{name}.")
            if nested_table:
                lines.append(nested_table)
                lines.append("")

            # Handle deeply nested objects
            for nested_name, nested_prop in prop["properties"].items():
                if nested_prop.get("type") == "object" and "properties" in nested_prop:
                    nested_desc = nested_prop.get("description", "")
                    lines.append(f"{'#' * (level + 2)} {name}.{nested_name}")
                    lines.append("")
                    if nested_desc:
                        lines.append(nested_desc)
                        lines.append("")

                    deep_table = generate_property_table(
                        nested_prop["properties"],
                        f"{name}.{nested_name}."
                    )
                    if deep_table:
                        lines.append(deep_table)
                        lines.append("")

    return "\n".join(lines)


def generate_toc(schemas: List[Dict[str, Any]]) -> str:
    """Generate table of contents."""
    lines = ["## Table of Contents", ""]

    for schema in schemas:
        title = schema.get("title", "Configuration")
        anchor = title.lower().replace(" ", "-").replace("/", "")
        lines.append(f"- [{title}](#{anchor})")

    lines.append("- [Environment Variable Quick Reference](#environment-variable-quick-reference)")
    lines.append("")
    return "\n".join(lines)


def main():
    """Generate documentation from schemas."""
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

    # Generate documentation
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    output = HEADER.format(timestamp=timestamp)
    output += generate_toc(schemas)

    for schema in schemas:
        output += generate_section(schema)
        output += "\n---\n\n"

    output += generate_env_var_reference(schemas)

    # Write output
    output_file = OUTPUT_DIR / "CONFIGURATION.md"
    with open(output_file, "w") as f:
        f.write(output)

    print(f"\nGenerated: {output_file}")
    print(f"  Schemas processed: {len(schemas)}")


if __name__ == "__main__":
    main()
