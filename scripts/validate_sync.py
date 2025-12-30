#!/usr/bin/env python3
"""
Validate that generated files are in sync with source schemas.

This script is designed for CI use - it regenerates all artifacts to a
temporary location and compares them with the committed versions.

Usage:
    python scripts/validate_sync.py

Exit codes:
    0 - All generated files are in sync
    1 - Generated files are out of sync (drift detected)
    2 - Generation failed

To fix drift:
    python scripts/validate_schemas.py --regenerate
    git add docs/generated src/generated web/api/models/generated
    git commit -m "chore: regenerate files from schemas"
"""

import hashlib
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"

# Files that should be generated and tracked
GENERATED_FILES = [
    "docs/generated/CONFIGURATION.md",
    "src/generated/config_types.h",
    "src/generated/config_defaults.h",
    "web/api/models/generated/config_models.py",
    "web/api/models/generated/__init__.py",
]

# Generators to run
GENERATORS = [
    "generate_docs.py",
    "generate_c_types.py",
    "generate_pydantic.py",
]


def compute_hash(path: Path) -> str:
    """Compute SHA256 hash of a file, ignoring timestamp lines.

    Timestamp lines are excluded from the hash to allow comparison between
    files generated at different times. We use regex patterns to match
    various timestamp formats that may appear in generated files.
    """
    if not path.exists():
        return ""

    content = path.read_text()

    # Patterns that match timestamp lines in generated files.
    # These patterns cover common formats used by generators:
    #   - "Generated at: 2024-12-30 15:30:00 UTC"
    #   - "Generated: 2024-12-30T15:30:00Z"
    #   - "* Generated at: ..."  (in C comments)
    #   - "# Generated at: ..."  (in Python comments)
    timestamp_patterns = [
        r'^\s*[#/*]*\s*Generated\s+(at:\s*)?\d{4}-\d{2}-\d{2}',  # ISO date format
        r'^\s*[#/*]*\s*Generated\s+at:\s+.+$',  # Generic "Generated at:" line
    ]
    combined_pattern = re.compile('|'.join(timestamp_patterns), re.IGNORECASE)

    lines = []
    for line in content.split('\n'):
        # Skip lines matching any timestamp pattern
        if combined_pattern.match(line):
            continue
        lines.append(line)

    normalized = '\n'.join(lines)
    return hashlib.sha256(normalized.encode()).hexdigest()


def run_generator(script: str) -> bool:
    """Run a generator script."""
    script_path = SCRIPTS_DIR / script

    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"  ERROR: {script} failed")
        print(f"  {result.stderr}")
        return False

    return True


def main():
    print("Validating generated files are in sync with schemas...\n")

    # Compute hashes of current committed files
    print("Computing hashes of committed files...")
    committed_hashes = {}
    for rel_path in GENERATED_FILES:
        full_path = REPO_ROOT / rel_path
        h = compute_hash(full_path)
        committed_hashes[rel_path] = h
        if h:
            print(f"  {rel_path}: {h[:12]}...")
        else:
            print(f"  {rel_path}: (missing)")

    print()

    # Run generators (they update files in place)
    print("Running generators...")
    for gen in GENERATORS:
        print(f"  {gen}...")
        if not run_generator(gen):
            print(f"\nFAILED: Generator {gen} failed")
            sys.exit(2)

    print()

    # Compute hashes of regenerated files
    print("Computing hashes of regenerated files...")
    regenerated_hashes = {}
    for rel_path in GENERATED_FILES:
        full_path = REPO_ROOT / rel_path
        h = compute_hash(full_path)
        regenerated_hashes[rel_path] = h
        if h:
            print(f"  {rel_path}: {h[:12]}...")
        else:
            print(f"  {rel_path}: (missing)")

    print()

    # Compare hashes
    drift_detected = False
    for rel_path in GENERATED_FILES:
        committed = committed_hashes.get(rel_path, "")
        regenerated = regenerated_hashes.get(rel_path, "")

        if committed != regenerated:
            if committed == "":
                print(f"DRIFT: {rel_path} - file is missing, needs to be generated")
            elif regenerated == "":
                print(f"DRIFT: {rel_path} - generation failed to create file")
            else:
                print(f"DRIFT: {rel_path} - content differs from schema")
            drift_detected = True

    if drift_detected:
        print()
        print("=" * 60)
        print("FAILED: Generated files are out of sync with schemas!")
        print()
        print("To fix this, run locally:")
        print("  python scripts/validate_schemas.py --regenerate")
        print("  git add docs/generated src/generated web/api/models/generated")
        print('  git commit -m "chore: regenerate files from schemas"')
        print("=" * 60)
        sys.exit(1)
    else:
        print("SUCCESS: All generated files are in sync with schemas.")
        sys.exit(0)


if __name__ == "__main__":
    main()
