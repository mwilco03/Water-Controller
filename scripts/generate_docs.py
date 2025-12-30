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


def has_extended_info(prop: Dict[str, Any], desc_threshold: int = 60) -> bool:
    """Check if property has extended info that warrants a details section."""
    desc = prop.get("description", "")
    has_long_desc = len(desc) > desc_threshold
    has_metadata = any(key in prop for key in [
        "x-env-var", "x-cli-arg", "x-unit", "x-sensitive", "x-readonly"
    ])
    return has_long_desc or has_metadata


def format_short_description(prop: Dict[str, Any], max_len: int = 60) -> str:
    """Format a short description for table cells."""
    desc = prop.get("description", "")

    # Add a marker if there's extended info
    if has_extended_info(prop, max_len):
        if len(desc) > max_len - 3:
            return desc[:max_len - 6] + "... ℹ️"
        return desc + " ℹ️"

    if len(desc) > max_len:
        return desc[:max_len - 3] + "..."

    return desc


def format_full_description(prop: Dict[str, Any]) -> List[str]:
    """Format full description with all metadata as a list of lines."""
    lines = []
    desc = prop.get("description", "")

    if desc:
        lines.append(desc)

    # Add metadata as a bullet list
    metadata = []
    if "x-env-var" in prop:
        metadata.append(f"**Environment variable**: `{prop['x-env-var']}`")
    if "x-cli-arg" in prop:
        metadata.append(f"**CLI argument**: `{prop['x-cli-arg']}`")
    if "x-unit" in prop:
        metadata.append(f"**Unit**: {prop['x-unit']}")
    if "x-sensitive" in prop and prop["x-sensitive"]:
        metadata.append("⚠️ **Sensitive** - This value should be kept secret")
    if "x-readonly" in prop and prop["x-readonly"]:
        metadata.append("*Read-only* - Cannot be modified at runtime")

    if metadata:
        lines.append("")
        for item in metadata:
            lines.append(f"- {item}")

    return lines


def generate_property_table(properties: Dict[str, Any], prefix: str = "") -> str:
    """Generate a Markdown table for properties.

    Uses short descriptions in the table. Properties with extended info
    (long descriptions or metadata) are marked with ℹ️ and detailed in
    a separate section generated by generate_property_details().
    """
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
        desc = format_short_description(prop)

        lines.append(f"| `{full_name}` | {type_str} | {default_str} | {desc} |")

    return "\n".join(lines)


def generate_property_details(properties: Dict[str, Any], prefix: str = "") -> str:
    """Generate detailed descriptions for properties with extended info.

    This creates a collapsible details section for each property that has:
    - A description longer than 60 characters
    - Metadata like environment variables, CLI arguments, units, etc.
    """
    details_props = []

    for name, prop in sorted(properties.items()):
        if prop.get("type") == "object" and "properties" in prop:
            continue
        if has_extended_info(prop):
            full_name = f"{prefix}{name}" if prefix else name
            details_props.append((full_name, prop))

    if not details_props:
        return ""

    lines = []
    lines.append("<details>")
    lines.append("<summary><strong>Parameter Details</strong> (click to expand)</summary>")
    lines.append("")

    for full_name, prop in details_props:
        lines.append(f"#### `{full_name}`")
        lines.append("")
        detail_lines = format_full_description(prop)
        lines.extend(detail_lines)
        lines.append("")

    lines.append("</details>")
    lines.append("")

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
    """Generate documentation section for a schema.

    For each group of properties, generates:
    1. A compact table with short descriptions
    2. A collapsible details section for properties with extended info
    """
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

    # Generate details section for top-level properties
    details = generate_property_details(properties)
    if details:
        lines.append(details)

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

            # Generate details for nested properties
            nested_details = generate_property_details(prop["properties"], f"{name}.")
            if nested_details:
                lines.append(nested_details)

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

                    # Generate details for deeply nested properties
                    deep_details = generate_property_details(
                        nested_prop["properties"],
                        f"{name}.{nested_name}."
                    )
                    if deep_details:
                        lines.append(deep_details)

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
