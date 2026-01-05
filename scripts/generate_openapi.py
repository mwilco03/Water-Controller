#!/usr/bin/env python3
"""
OpenAPI Specification Generator

Generates OpenAPI specification from the FastAPI application.
The spec can be used for client generation, documentation, and API testing.

Usage:
    python scripts/generate_openapi.py                    # Generate openapi.json
    python scripts/generate_openapi.py --yaml             # Generate openapi.yaml
    python scripts/generate_openapi.py --output api.json  # Custom output path

Output:
    docs/api/openapi.json (or .yaml)
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Add web/api to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "web" / "api"))

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


def get_openapi_spec():
    """Generate OpenAPI spec from FastAPI app."""
    try:
        from app.main import app
        return app.openapi()
    except ImportError as e:
        print(f"ERROR: Could not import FastAPI app: {e}", file=sys.stderr)
        print("Make sure you're running from the project root and dependencies are installed.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Failed to generate OpenAPI spec: {e}", file=sys.stderr)
        sys.exit(1)


def write_json(spec: dict, output_path: Path):
    """Write spec as JSON."""
    with open(output_path, "w") as f:
        json.dump(spec, f, indent=2)
    print(f"OpenAPI spec written to: {output_path}")


def write_yaml(spec: dict, output_path: Path):
    """Write spec as YAML."""
    if not HAS_YAML:
        print("ERROR: PyYAML not installed. Run: pip install pyyaml", file=sys.stderr)
        sys.exit(1)

    with open(output_path, "w") as f:
        yaml.dump(spec, f, default_flow_style=False, sort_keys=False)
    print(f"OpenAPI spec written to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate OpenAPI specification")
    parser.add_argument(
        "--output", "-o",
        help="Output file path (default: docs/api/openapi.json)"
    )
    parser.add_argument(
        "--yaml",
        action="store_true",
        help="Output as YAML instead of JSON"
    )
    parser.add_argument(
        "--print",
        action="store_true",
        dest="print_spec",
        help="Print spec to stdout instead of file"
    )
    args = parser.parse_args()

    # Generate spec
    print("Generating OpenAPI specification from FastAPI app...")
    spec = get_openapi_spec()

    # Add custom metadata
    spec["info"]["x-generator"] = "generate_openapi.py"
    spec["info"]["x-generated-at"] = __import__("datetime").datetime.now().isoformat()

    if args.print_spec:
        if args.yaml:
            if not HAS_YAML:
                print("ERROR: PyYAML not installed", file=sys.stderr)
                sys.exit(1)
            print(yaml.dump(spec, default_flow_style=False, sort_keys=False))
        else:
            print(json.dumps(spec, indent=2))
        return

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        output_dir = PROJECT_ROOT / "docs" / "api"
        output_dir.mkdir(parents=True, exist_ok=True)
        ext = "yaml" if args.yaml else "json"
        output_path = output_dir / f"openapi.{ext}"

    # Write spec
    if args.yaml or str(output_path).endswith((".yaml", ".yml")):
        write_yaml(spec, output_path)
    else:
        write_json(spec, output_path)

    # Print summary
    print(f"\nAPI Summary:")
    print(f"  Title: {spec['info']['title']}")
    print(f"  Version: {spec['info']['version']}")
    print(f"  Paths: {len(spec.get('paths', {}))}")
    print(f"  Schemas: {len(spec.get('components', {}).get('schemas', {}))}")


if __name__ == "__main__":
    main()
